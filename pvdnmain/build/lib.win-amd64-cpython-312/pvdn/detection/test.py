import argparse
import os
import shutil
import json
from warnings import warn
import torch
from torchvision.transforms import ToTensor
from ptflops import get_model_complexity_info

from pvdn import BoundingBoxDataset
from pvdn.metrics.bboxes import BoundingBoxEvaluator, evaluate
from pvdn.detection.model.single_flow_classifier import Classifier
from pvdn.detection.engine import val_one_epoch
from pvdn.metrics.convert import result_to_coco_format
from pvdn.detection.train import device_available


def test(data_path, conf_thresh, output_dir, model_path, save_coco, plot_scenes,
         device, bs=64,
         n_workers=16):
    torch.multiprocessing.set_sharing_strategy('file_system')

    # set up output path
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        print(f"Creating output directory: {output_dir}")
        os.mkdir(output_dir)
    if plot_scenes:
        scene_dir = os.path.join(output_dir, "scenes")
        if os.path.isdir(scene_dir):
            shutil.rmtree(scene_dir)
        os.mkdir(scene_dir)

    # check device
    if not device_available(device):
        device = "cpu"
    print(f"Device:\t{device}")

    # set up data
    testset = BoundingBoxDataset(data_path, transform=ToTensor())
    testloader = torch.utils.data.DataLoader(testset,
                                             batch_size=bs,
                                             shuffle=False,
                                             num_workers=n_workers)

    model = Classifier()

    # get model stats
    in_shape = tuple(testset[0][0].shape)
    macs, params = get_model_complexity_info(model, in_shape, as_strings=False,
                                             print_per_layer_stat=True,
                                             verbose=True)
    gflops = macs / 1000000000 * 2
    print("-----------------------------\n"
          "Model complexity:\n"
          f"\tFLOPs:\t{round(gflops, 2)} GFLOPs\n"
          f"\tParams:\t{params}\n"
          f"-----------------------------")

    try:
        model.load_state_dict(torch.load(os.path.abspath(model_path))["model"])
    except KeyError:
        model.load_state_dict(torch.load(os.path.abspath(model_path)))

    _, predictions = val_one_epoch(model=model, dataloader=testloader,
                                   criterion=None,
                                   device=device)

    evaluator = BoundingBoxEvaluator(data_dir=data_path)
    metrics = evaluate(evaluator, conf_thresh,
                       predictions)

    with open(os.path.join(output_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f)
    print(f"Saved metrics to {os.path.join(output_dir, 'metrics.json')}")

    if plot_scenes:
        print(f"Plotting scenes {', '.join(plot_scenes)} ...")
        testset.plot_scenes(scene_ids=plot_scenes, preds=predictions,
                            output_dir=scene_dir, conf_thresh=conf_thresh)
        print(
            f"Saved results of scenes {', '.join(plot_scenes)} to {scene_dir}.")

    with open(os.path.join(output_dir, "predictions.json"), "w") as f:
        json.dump(predictions, f)
    print(
        f"Saved predictions to {os.path.join(output_dir, 'predictions.json')}")

    if save_coco:
        coco_preds = result_to_coco_format(predictions)
        with open(os.path.join(output_dir, "predictions_coco.json"), "w") as f:
            json.dump(coco_preds, f)
        print(
            f"Saved predictions to {os.path.join(output_dir, 'predictions_coco.json')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test_data", type=str,
                        default="/home/lukas/Development/datasets/PVDN/day/test",
                        help="Path to the test split.")
    parser.add_argument("--output_dir", type=str, default="runs/test",
                        help="Path to results ")
    parser.add_argument("--model_path", type=str,
                        default="weights_pretrained.pt")
    parser.add_argument("--device", choices=("cuda", "cpu"), type=str,
                        default="cuda",
                        help="cuda or cpu")
    parser.add_argument("--save_coco", action="store_true",
                        help="Flag to save the predictions also in coco results format.")
    parser.add_argument("--plot_scenes", nargs="+",
                        help="Scene ids to be plotted and saved.")
    parser.add_argument("--batch_size", type=int, default=64,
                        help="Batch size.")
    parser.add_argument("--workers", type=int, default=16,
                        help="Number of workers to use for "
                             "dataloader.")
    parser.add_argument("--conf_thresh", type=float, default=0.5,
                        help="Confidence threshold at which to classify positive.")
    args = parser.parse_args()

    test(args.test_data, args.conf_thresh, args.output_dir, args.model_path,
         args.save_coco, args.plot_scenes, args.device, args.batch_size,
         args.workers)
