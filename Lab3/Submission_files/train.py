import argparse
import pickle
import ssl
import os

import torch.optim as optim
import torch.nn as nn
import torchvision
from torch.utils.data import DataLoader, Dataset
import matplotlib.pyplot as plt
import torch
import torchvision.transforms as transforms
import time as t

import vanilla_model as vanilla
import moded_model as moded

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
def evaluate_epoch_top1_5(model, data, device, test_loader=None):
    model.eval() #Set to evaluate
    tot_top1_accuracy = 0
    tot_top5_accuracy = 0
    test_tot_top1_accuracy = 0
    test_tot_top5_accuracy = 0
    for imgs, labels in data:
        imgs = imgs.to(device)
        labels = labels.to(device)

        with torch.no_grad():
            output = model(imgs)
        curr_top1, curr_top5 = get_output_accuracy(output, labels, (1, 5))
        tot_top1_accuracy += curr_top1
        tot_top5_accuracy += curr_top5
    avg_test_top5_epoch_acc = 0
    avg_test_top1_epoch_acc = 0
    if test_loader is not None:
        for imgs, labels in test_loader:
            imgs = imgs.to(device)
            labels = labels.to(device)

            with torch.no_grad():
                output = model(imgs)
            curr_top1, curr_top5 = get_output_accuracy(output, labels, (1, 5))
            test_tot_top1_accuracy += curr_top1
            test_tot_top5_accuracy += curr_top5
    avg_test_top5_epoch_acc = test_tot_top5_accuracy / len(test_loader)
    avg_test_top1_epoch_acc = test_tot_top1_accuracy / len(test_loader)
    avg_top5_epoch_acc = tot_top5_accuracy / len(data)
    avg_top1_epoch_acc = tot_top1_accuracy / len(data)

    model.train() #Set to train when returning to function

    return avg_top1_epoch_acc, avg_top5_epoch_acc, avg_test_top1_epoch_acc, avg_test_top5_epoch_acc

def train(n_epochs, optimizer, model, loss_fn, train_loader, scheduler, device,
          decoder_save=None, plot_file=None, pickleLosses = None,
          starting_epoch=1, evaluate_epochs=False, folder='./', store_data=False, test_loader=None):

    model.train()
    total_losses = []
    total_top1_accuracy = []
    total_top5_accuracy = []
    test_total_top1_accuracy = []
    test_total_top5_accuracy = []

    final_loss = 0.0
    t_1 = t.time()
    print("\n=======================================")
    print("Training started at Epoch {}\n".format(starting_epoch))

    # loading_saved pickle data
    # if pickleLosses is not None:
    #     try:
    #         with open(pickleLosses, 'rb') as file:
    #             loaded_losses = pickle.load(file)
    #             (total_losses, content_losses, style_losses) = loaded_losses
    #             print("Loaded saved losses from file successfully: \n{} \n{} \n{}"
    #                   .format(total_losses, content_losses, style_losses))
    #     except Exception as e:
    #         print(f"An error occurred while loading arrays: {str(e)}")


    for epoch in range(starting_epoch, n_epochs + 1):
        print("Starting Epoch: ", epoch)
        # Losses for current epoch
        total_loss = 0.0
        t_2 = t.time()

        for idx, data in enumerate(train_loader):
            t_3 = t.time()
            imgs, labels = data[0].to(device), data[1].to(device)
            optimizer.zero_grad()

            outputs = model(imgs)
            loss = loss_fn(outputs, labels)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            print('Batch #{}/{}         Time: {}'.format(idx + 1, len(train_loader), (t.time() - t_3)))

        if decoder_save is not None and (epoch % 50 == 0 or epoch == n_epochs):
            torch.save(model.decoder.state_dict(), decoder_save)
            print("Saved frontend model under name: {}".format(decoder_save))

        scheduler.step(total_loss)
        total_losses.append(total_loss / len(train_loader))
        final_loss = total_loss / len(train_loader)

        # Store loss data in pickled file
        # pickleSave = os.path.join(os.path.abspath(folder), "pickled_dump.pk1")
        # if pickleLosses is not None:
        #     pickleSave = os.path.join(os.path.abspath(folder), pickleLosses)
        # try:
        #     with open(pickleSave, 'wb') as file:
        #         pickle.dump((total_losses, epoch), file)
        #         print("Saved losses to '{}'".format(pickleSave))
        # except Exception as e:
        #     print(f"An error occurred while saving arrays: {str(e)}")

        # Plot loss data each epoch
        if plot_file is not None:
            plot_save = os.path.join(os.path.abspath(folder), plot_file)
            plt.figure(2, figsize=(12, 7))
            plt.clf()
            plt.plot(total_losses, label='Total')
            plt.xlabel('epoch')
            plt.ylabel('loss')
            plt.legend(loc=1)
            plt.savefig(plot_save)

        print('Epoch {}, Training loss {}, Time  {}'.format(epoch, final_loss,(t.time() - t_2)))
        if evaluate_epochs:
            top_1_acc, top_5_acc, test_top_1_acc, test_top_5_acc = evaluate_epoch_top1_5(model, train_loader, device, test_loader=test_loader)
            total_top1_accuracy.append(float(top_1_acc))
            total_top5_accuracy.append(float(top_5_acc))
            print("Accuracy (Training Data) = TOP-1:   {}  |  TOP-5:    {}".format(top_1_acc, top_5_acc))
            if test_loader is not None:
                test_total_top1_accuracy.append(float(test_top_1_acc))
                test_total_top5_accuracy.append(float(test_top_5_acc))
            print("Accuracy (Test Data) = TOP-1:   {}  |  TOP-5:    {}".format(test_top_1_acc, test_top_5_acc))

    print('Total Training loss {}, Time  {}'.format(final_loss, (t.time() - t_1)))

    # if store_data:
    #     filename = os.path.join(os.path.abspath(folder), 'output_results')
    #     print("Length: {}    {}   {}    {}   {}".format(total_top5_accuracy, total_top1_accuracy, test_total_top1_accuracy, test_total_top5_accuracy, total_losses))
    #     try:
    #         with open(filename, 'w') as file:
    #             file.write("Training results for run with the following hyper parameters:\n{}\n".format(arguments))
    #             if train_loader is not None: file.write("Accuracy & loss results per Epoch: (Train_Top 1,  Train_Top 5, "
    #                                                     "Test_Top_1, Test_Train_5,  Loss)\n")
    #             else: file.write("Accuracy & loss results per Epoch: (Top 1,    Top 5,   Loss)\n")
    #             for i in range(n_epochs):
    #                 top_1_item = total_top1_accuracy[i]
    #                 top_5_item = total_top5_accuracy[i]
    #                 test_top_5, test_top_1 = "", ""
    #                 if train_loader is not None:
    #                     test_top_1 = test_total_top1_accuracy[i]
    #                     test_top_5 = test_total_top5_accuracy[i]
    #
    #                 loss = total_losses[i]
    #                 file.write("Epoch {}:  ([{},  {}],   [{},   {}],   {})\n".format(i + 1, top_1_item, top_5_item, test_top_1, test_top_5, loss))
    #             file.close()
    #
    #     except Exception as e:
    #         print(f"An error occurred while loading arrays: {str(e)}")
    return final_loss


if __name__ == '__main__':

    # ssl._create_default_https_context = ssl._create_unverified_context

    device = 'cpu'
    # Setup parser
    parser = argparse.ArgumentParser()
    parser.add_argument('-dir', '--dir', type=str, required=False, default='./data',
                        help='Directory path to a batch of content images')
    # training options
    parser.add_argument('-e', '--e', type=int, default=50)
    parser.add_argument('-b', '--b', type=int, default=8, help="Batch size")
    parser.add_argument('-l', '--l', help="Encoder.pth", required=True)
    parser.add_argument('-s', '--s', help="Decoder.pth")
    parser.add_argument('-p', '--p', help="decoder.png")
    parser.add_argument('-cuda', '--cuda', default='Y')
    parser.add_argument('-type', '--type', type=int, default=0)


    parser.add_argument('-lr', '--lr', type=float, default=0.001)
    parser.add_argument('-wd', '--wd', type=float, default=0.00001)
    parser.add_argument('-minlr', '--minlr', type=float, default=0.001)
    parser.add_argument('-out', '--out', default=None, help="Output folder to put all files for training run")
    parser.add_argument('-gamma', '--gamma', type=float, default=0.9)
    parser.add_argument('-dataset', '--dataset', type=int, default=1)

    args = parser.parse_args()

    print("Beginning Training for model. Using the following parameters passed (Some default)\n")
    print("")

    if args.type == 0:
        model_type = vanilla
    else:
        model_type = moded

    # Import the dataset & get num of batches
    train_transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
    if args.dataset == 0:
        cifar_dataset = torchvision.datasets.CIFAR10(root='./data', train=True, download=True, transform=train_transform)
        cifar_test_dataset = torchvision.datasets.CIFAR10(root='./data', train=False, download=True,
                                                           transform=train_transform)
        cifar_data = DataLoader(cifar_dataset, batch_size=args.b, shuffle=True)
        cifar_test_data = DataLoader(cifar_test_dataset, batch_size=args.b, shuffle=True)
        frontend = model_type.encoder_decoder.frontend_10

    else:
        cifar_dataset = torchvision.datasets.CIFAR100(root='./data', train=True, download=True, transform=train_transform)
        cifar_test_dataset = torchvision.datasets.CIFAR100(root='./data', train=False, download=True, transform=train_transform)
        cifar_data = DataLoader(cifar_dataset, batch_size=args.b, shuffle=True)
        cifar_test_data = DataLoader(cifar_test_dataset, batch_size=args.b, shuffle=True)
        frontend = model_type.encoder_decoder.frontend

    encoder = model_type.encoder_decoder.encoder
    encoder.load_state_dict(torch.load(args.l))


    # Creating folder to store all files made during training
    if args.out != None:
        if os.path.exists(os.path.abspath(args.out)):
            print("Saving all files created to folder '{}'".format(args.out))
        else:
            os.mkdir(args.out)
            print("Created folder {} to save all files made during training".format(args.out))
    else:
        args.out = "./"

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
    model = model_type.model(encoder, frontend)
    model.to(device)

    # Define optimizer and learning rate scheduler
    optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.wd)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=2, verbose=True, factor=0.1,
                                                     min_lr=args.minlr)

    # Train the model
    train(args.e, optimizer, model, loss_fn, cifar_data, scheduler, device, args.s,
          args.p, evaluate_epochs=False, folder=args.out, store_data=True, test_loader=cifar_test_data)
