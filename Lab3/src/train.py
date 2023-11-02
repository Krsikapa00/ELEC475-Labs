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
def evaluate_epoch_top1_5(model, data):
    model.eval() #Set to evaluate
    tot_top1_accuracy = 0
    tot_top5_accuracy = 0
    for imgs, labels in data:
        with torch.no_grad():
            output = model(imgs)
        curr_top1, curr_top5 = get_output_accuracy(output, labels, (1, 5))
        tot_top1_accuracy += curr_top1
        tot_top5_accuracy += curr_top5
    avg_top5_epoch_acc =  tot_top5_accuracy/len(data)
    avg_top1_epoch_acc =  tot_top1_accuracy/len(data)
    model.train() #Set to train when returning to function

    return avg_top1_epoch_acc, avg_top5_epoch_acc

def train(n_epochs, optimizer, model, loss_fn, train_loader, scheduler, device,
          decoder_save=None, plot_file=None, pickleLosses = None,
          starting_epoch=1, evaluate_epochs=False, accuracy_file_name=None, folder='./', store_data=False):

    model.train()
    total_losses = []
    total_top1_accuracy = []
    total_top5_accuracy = []
    final_loss = 0.0
    t_1 = t.time()
    print("\n=======================================")
    print("Training started at Epoch {}\n".format(starting_epoch))

    # loading_saved pickle data
    if pickleLosses is not None:
        try:
            with open(pickleLosses, 'rb') as file:
                loaded_losses = pickle.load(file)
                (total_losses, content_losses, style_losses) = loaded_losses
                print("Loaded saved losses from file successfully: \n{} \n{} \n{}"
                      .format(total_losses, content_losses, style_losses))
        except Exception as e:
            print(f"An error occurred while loading arrays: {str(e)}")


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

        if decoder_save is not None:
            savedir = os.path.join(os.path.abspath(folder), str(epoch) + '_' + decoder_save)
            torch.save(model.decoder.state_dict(), savedir)
            print("Saved frontend model under name: {}".format(savedir))

        scheduler.step(total_loss)
        total_losses.append(total_loss / len(train_loader))
        final_loss = total_loss / len(train_loader)

        # Store loss data in pickled file
        pickleSave = os.path.join(os.path.abspath(folder), "pickled_dump.pk1")
        if pickleLosses is not None:
            pickleSave = os.path.join(os.path.abspath(folder), pickleLosses)
        try:
            with open(pickleSave, 'wb') as file:
                pickle.dump((total_losses, epoch), file)
                print("Saved losses to '{}'".format(pickleSave))
        except Exception as e:
            print(f"An error occurred while saving arrays: {str(e)}")

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
        epoch_accuracy = 0
        if evaluate_epochs:
            top_1_acc, top_5_acc = evaluate_epoch_top1_5(model, train_loader)
            total_top1_accuracy.append(float(top_1_acc))
            total_top5_accuracy.append(float(top_5_acc))
            print("Accuracy= TOP-1:   {}  |  TOP-5:    {}".format(top_1_acc, top_5_acc))

    print('Total Training loss {}, Time  {}'.format(final_loss, (t.time() - t_1)))

    if store_data:
        filename = os.path.join(os.path.abspath(folder), 'output_results')
        print("Length: {}    {}   {}".format(total_top5_accuracy, total_top1_accuracy, total_losses))
        try:
            with open(filename, 'w') as file:
                file.write("Accuracy & loss results per Epoch: (Top 1,    Top 5,   Loss)\n")
                for i in range(n_epochs):
                    top_1_item = total_top1_accuracy[i]
                    top_5_item = total_top5_accuracy[i]
                    loss = total_losses[i]
                    file.write("Epoch {}:  ({}   ,{},    {})\n".format(i + 1, top_1_item, top_5_item, loss))
                file.close()

        except Exception as e:
            print(f"An error occurred while loading arrays: {str(e)}")
    return final_loss


if __name__ == '__main__':

    ssl._create_default_https_context = ssl._create_unverified_context

    device = 'cpu'
    # Setup parser
    parser = argparse.ArgumentParser()
    parser.add_argument('-dir', '--dir', type=str, required=False,
                        help='Directory path to a batch of content images')
    # training options
    parser.add_argument('-e', '--e', type=int, default=50)
    parser.add_argument('-b', '--b', type=int, default=8, help="Batch size")
    parser.add_argument('-l', '--l', help="Encoder.pth", required=True)
    parser.add_argument('-s', '--s', help="Decoder.pth")
    parser.add_argument('-p', '--p', help="decoder.png")
    parser.add_argument('-cuda', '--cuda', default='Y')

    # Optional multi-version training options
    parser.add_argument('-opt', '--opt', type=int, default=0, help="optimizer to choose")
    parser.add_argument('-sch', '--sch', type=int, default=0, help="scheduler to choose")
    parser.add_argument('-frontend', '--frontend', type=int, default=0, help="frontend to choose")

    parser.add_argument('-lr', '--lr', type=float, default=0.001)
    parser.add_argument('-minlr', '--minlr', type=float, default=0.001)
    parser.add_argument('-prefix', '--prefix', help="File name prefix to use for model, plot, pickle files saved")
    parser.add_argument('-out', '--out', default="./", help="Output folder to put all files for training run")
    parser.add_argument('-momentum', '--momentum', type=float, default=0.7)
    parser.add_argument('-gamma', '--gamma', type=float, default=0.9)

    # Optional long training options (when need to start between epochs)
    parser.add_argument('-starting_epoch', '--starting_epoch', type=int, help="3", default=1)
    parser.add_argument('-starting_decoder', '--starting_decoder', help="#_decoder.pth")
    parser.add_argument('-starting_pickle', '--starting_pickle', help="pickledLosses.pk1", default=None)

    args = parser.parse_args()

    print("Beginning Training for model. Using the following parameters passed (Some default)\n")
    print(args)
    print("")

    # Import the dataset & get num of batches
    train_transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
    cifar_dataset = torchvision.datasets.CIFAR10(root='./data', train=True, download=True, transform=train_transform)
    cifar_data = DataLoader(cifar_dataset, batch_size=args.b, shuffle=True)


    # Creating folder to store all files made during training
    if args.out != "./":
        if os.path.exists(os.path.abspath(args.out)):
            print("Saving all files created to folder '{}'".format(args.out))
        else:
            os.mkdir(args.out)
            print("Created folder {} to save all files made during training".format(args.out))


    # Set the device (GPU if available, otherwise CPU)
    if torch.cuda.is_available() and args.cuda == 'Y':
        if torch.cuda.device_count() > 1:
            device = torch.device("cuda:1")
        else:
            device = torch.device("cuda:0")
    else:
        device = torch.device("cpu")

    print("Using device: {}".format(device))


    # Create models
    # PURELY FOR TRAINING, let me choose which frontend to use
    if args.frontend == 0:
        frontend = vanilla.encoder_decoder.frontend
    elif args.frontend == 1:
        frontend = vanilla.encoder_decoder.frontend1
    elif args.frontend == 2:
        frontend = vanilla.encoder_decoder.frontend2
    else:
        frontend = vanilla.encoder_decoder.frontend

    # elif args.frontend == 0:

    encoder = vanilla.encoder_decoder.encoder
    encoder.load_state_dict(torch.load(args.l))
    loss_fn = nn.functional.cross_entropy

    vanilla_model = vanilla.vanilla_model(encoder, frontend)
    vanilla_model.to(device)


    # Define optimizer and learning rate scheduler
    # TODO: Put final optimizer and scheduler below
    # optimizer =
    # scheduler =

    # PURELY FOR TRAINING AND SWITCHING OPT AND SCHEDULERS
    if args.opt == 0:
        optimizer = optim.SGD(vanilla_model.parameters(), lr=args.lr, momentum=args.momentum)
    elif args.out == 1:
        optimizer = optim.Adam(vanilla_model.parameters(), lr=args.lr, weight_decay=1e-5)
    else:
        optimizer = optim.Adam(vanilla_model.parameters(), lr=args.lr, weight_decay=1e-5)


    if args.sch == 0:
        if args.e <= 10 and args.e > 6:
            milestones = [int(args.e/3), int((2*args.e)/3), int(args.e)]
        elif args.e <= 20:
            milestones = [int(args.e/4), int((2*args.e)/4), int((3*args.e)/4), int(args.e)]
        else:
            milestones = [1]
        scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=milestones, gamma=args.gamma)
    elif args.sch == 1:
        scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma=args.gamma)
    else:
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=5, verbose=True, factor=0.1,
                                                         min_lr=args.minlr)

    # Train the model
    train(args.e, optimizer, vanilla_model, loss_fn, cifar_data, scheduler, device, args.s,
          args.p, pickleLosses=args.starting_pickle, evaluate_epochs=True, folder=args.out, store_data=True)
