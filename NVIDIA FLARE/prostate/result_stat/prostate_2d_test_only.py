# Copyright (c) 2021-2022, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# TODO: create directories where transformed images, transformed labels and predictions are saved
# Under result_stat/
# images_trans_2D, labels_trans_2D, predictions_2D

import argparse

import torch
from monai.data import CacheDataset, DataLoader, load_decathlon_datalist
from monai.inferers import SimpleInferer
from monai.metrics import DiceMetric
from monai.networks.nets import UNet
from monai.transforms import (
    Activations,
    AsDiscrete,
    AsDiscreted,
    Compose,
    EnsureChannelFirstd,
    EnsureType,
    EnsureTyped,
    LoadImaged,
    Resized,
    ScaleIntensityRanged,
)
# TODO: add import: save_image
from torchvision.utils import save_image


def main():
    parser = argparse.ArgumentParser(description="Model Testing")
    parser.add_argument("--model_path", type=str)
    parser.add_argument("--cache_rate", default=1.0, type=float)
    parser.add_argument("--dataset_base_dir", default="../data_preparation/dataset_2D", type=str)
    parser.add_argument("--datalist_json_path", default="../data_preparation/datalist_2D/client_All.json", type=str)
    args = parser.parse_args()

    # Set basic settings and paths
    dataset_base_dir = args.dataset_base_dir
    datalist_json_path = args.datalist_json_path
    model_path = args.model_path
    cache_rate = args.cache_rate

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # Set datalists
    test_list = load_decathlon_datalist(
        data_list_file_path=datalist_json_path,
        is_segmentation=True,
        data_list_key="testing",
        base_dir=dataset_base_dir,
    )
    print(f"Testing Size: {len(test_list)}")

    # Network, optimizer, and loss
    model = UNet(
        dimensions=2,
        in_channels=1,
        out_channels=1,
        channels=(16, 32, 64, 128, 256),
        strides=(2, 2, 2, 2),
        num_res_units=2,
    ).to(device)
    model_weights = torch.load(model_path)
    model_weights = model_weights["model"]
    model.load_state_dict(model_weights)

    # Inferer, evaluation metric
    inferer = SimpleInferer()
    valid_metric = DiceMetric(include_background=False, reduction="mean", get_not_nans=False)

    transform = Compose(
        [
            LoadImaged(keys=["image", "label"]),
            EnsureChannelFirstd(keys=["image", "label"]),
            ScaleIntensityRanged(keys=["image", "label"], a_min=0, a_max=255, b_min=0.0, b_max=1.0),
            Resized(keys=["image", "label"], spatial_size=(256, 256), mode=("bilinear"), align_corners=True),
            AsDiscreted(keys=["label"], threshold=0.5),
            EnsureTyped(keys=["image", "label"]),
        ]
    )
    transform_post = Compose([EnsureType(), Activations(sigmoid=True), AsDiscrete(threshold=0.5)])

    # Set dataset
    test_dataset = CacheDataset(
        data=test_list,
        transform=transform,
        cache_rate=cache_rate,
        num_workers=4,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=1,  # !!!
        shuffle=False,  # TODO: Does that mean that the model is tested on data following the order defined in datalist?
                        # Yes basically
        num_workers=1,
    )

    # Train
    model.eval()
    with torch.no_grad():  # Basically the same code as validation (local_valid() in supervised_learner.py)
        metric = 0
        for i, batch_data in enumerate(test_loader):
            images = batch_data["image"].to(device)
            labels = batch_data["label"].to(device)
            # Inference
            outputs = inferer(images, model)
            outputs = transform_post(outputs)

            # TODO: Add print() to get type and shape of outputs
            print(type(outputs))  # torch.tensor
            print(outputs.shape)  # torch.Size([1, 1, 256, 256])

            # TODO: Save outputs
            print(i)
            outputs_2D = outputs[0, 0, :, :]
            print(outputs_2D.shape)  # torch.Size([256, 256])
            save_image(outputs_2D, f'predictions_2D/pred{i}.png')
                # Works when batch_size = 1
                # → all the i (and therefore all the saved img names) will be different
                # predictions_2D folder has to exist before running this script

            # TODO: Save transformed images and labels → to compare with pred
            # print(type(images), images.shape)
            # print(type(images), labels.shape)
            # images and labels shape: torch.Size([1, 1, 256, 256])
            images_2D = images[0, 0, :, :]
            labels_2D = labels[0, 0, :, :]
            save_image(images_2D, f'images_trans_2D/img_trans{i}.png')
            save_image(labels_2D, f'labels_trans_2D/label_trans{i}.png')

            # Compute metric
            metric_score = valid_metric(y_pred=outputs, y=labels)
            metric += metric_score.item()
        # compute mean dice over whole validation set
        metric /= len(test_loader)
        print(f"Test Dice: {metric:.4f}")


if __name__ == "__main__":
    main()
