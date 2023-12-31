import argparse
import pickle
import ssl
import os
import datetime

import torch.optim as optim
import torch.nn as nn
import torchvision
from torch.utils.data import DataLoader, Dataset
import matplotlib.pyplot as plt
import torch
import torchvision.transforms as transforms
import time as t

import YodaModel as model
import KiitiROIDataset as KittiData



def get_output_accuracy(pred, confirmed, top_res=(1,)):
    max_num_results = max(top_res) #get highest result looking for
    data_size = confirmed.size(0)

    pred_values, pred_indx = pred.topk(k=max_num_results, dim=1)
    pred_indx = pred_indx.t()
#   Reshape confirmed indxs
    confirmed_indx_reshape = confirmed.view(1, -1).expand_as(pred_indx)
    answers = pred_indx == confirmed_indx_reshape

    top_res_acc = []
    for k in top_res:
        temp_answers = answers[:k] #limit each image answer to k values
        temp_answers = temp_answers.reshape(-1).float() #flatten to see whats right form ALL images in batch
        temp_answers = temp_answers.float().sum(dim=0, keepdim=True)
        curr_acc = temp_answers/data_size
        top_res_acc.append(curr_acc)
    return top_res_acc

def eval_acc_for_epoch(data, model, device, train=False):
    tot_top1_accuracy = 0
    truePos, trueNeg, falsePos, falseNeg = 0, 0, 0, 0
    type = "Test Data"
    if train:
        type = "Train Data"
    for idx, (imgs, labels) in enumerate(data):
        imgs = imgs.to(device)
        labels = labels.to(device)

        with torch.no_grad():
            output = model(imgs)

        [curr_top1] = get_output_accuracy(output, labels, (1,))
        tot_top1_accuracy += curr_top1
        output_rounded = torch.argmax(output, dim=1)
        truePos += torch.sum((output_rounded == 1) & (labels == 1)).item()
        trueNeg += torch.sum((output_rounded == 0) & (labels == 0)).item()
        falsePos += torch.sum((output_rounded == 1) & (labels == 0)).item()
        falseNeg += torch.sum((output_rounded == 0) & (labels == 1)).item()

        if idx == 1:
            break

        print("{} Accuracy progress: {}/{}".format(type, idx, len(data)))
    return tot_top1_accuracy, (truePos, trueNeg, falsePos, falseNeg)

def evaluate_epoch_acc(model, data, device, test_loader=None):
    tot_top1_accuracy = 0
    test_tot_top1_accuracy = 0
    print("Accuracy for Test Data:")
    tot_top1_accuracy, confusion_matrix = eval_acc_for_epoch(data, model, device)
    avg_test_top1_epoch_acc = 0
    test_confusion_matrix = ()


    avg_top1_epoch_acc = tot_top1_accuracy / len(data)

    return avg_top1_epoch_acc, avg_test_top1_epoch_acc, confusion_matrix, test_confusion_matrix


if __name__ == '__main__':

    # ssl._create_default_https_context = ssl._create_unverified_context

    device = 'cpu'
    # Setup parser
    parser = argparse.ArgumentParser()
    parser.add_argument('-dir', '--dir', type=str, required=True,
                        help='Directory path where all the Kitti_ROIs train and test images are held, dont include train or test folder')
    # training options
    parser.add_argument('-e', '--e', type=int, default=40)
    parser.add_argument('-b', '--b', type=int, default=256, help="Batch size")
    parser.add_argument('-l', '--l', help="filename to load saved encoder; Encoder.pth", required=False)
    parser.add_argument('-cuda', '--cuda', default='Y')

    args = parser.parse_args()

    print("Beginning Training for model. Using the following parameters passed (Some default)\n")
    print("\n{}".format(args))

    # Import the dataset & get num of batches
    train_dir = os.path.join(os.path.abspath(args.dir), 'train')
    test_dir = os.path.join(os.path.abspath(args.dir), 'test')

    train_transform = transforms.Compose([transforms.ToTensor(), transforms.Resize((150, 150))])
    kitti_train_dataset = KittiData.KittiROIDataset(train_dir, training=True, transform=train_transform)
    kitti_test_dataset = KittiData.KittiROIDataset(test_dir, training=False, transform=train_transform)

    test_data = DataLoader(kitti_test_dataset, batch_size=args.b, shuffle=False)

    model = model.model()

    if args.l is not None:
        model.load_state_dict(torch.load(args.l))

    # Set the device (GPU if available, otherwise CPU)
    if torch.cuda.is_available() and args.cuda == 'Y':
        if torch.cuda.device_count() > 1:
            device = torch.device("cuda:1")
        else:
            device = torch.device("cuda:0")
    else:
        device = torch.device("cpu")

    print("Using device: {}".format(device))

    loss_fn = nn.functional.cross_entropy
    model.to(device)
    model.eval()

    avg_acc, avg_test_acc, confusion_matrix, test_confusion_matrix = evaluate_epoch_acc(model, test_data, device)

    print("Accuracy Percentage: {}%".format(float(avg_acc * 100)))
    print("Confusion matrix: {}".format(confusion_matrix))
