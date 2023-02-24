import time
import torch
import os
from tqdm import tqdm
import sys
from torch.utils.data import DataLoader
import pathlib

from datasetOp.dataset_taxibj import DataSetTaxiBJ, traffNet_collect_fn
from model.PredTaxiBJModel_taxibj import PredTraffModel_taxibj
from utils.utils import getSeqMaxSize

# 加载模型超参数

folder = pathlib.Path(__file__).parent.parent.resolve()
seq_max_size = getSeqMaxSize(os.path.join(folder, "data/pathNodeDict_TaxiBj.txt"))

window_width = 3
batch_size = 2
edgeNum = 81
horizon = 7
lr = 0.00005
epochs = 10000
device = torch.device('cuda:0')

# 训练集，测试集，验证集的长度
timestampsTrain = 20 * 24 * 4
timestampsVal = 20 * 24 * 1
timestampsTest = 20 * 24 * 2
# 训练集，测试集，验证集开始的索引
train_start_idx = 0
val_start_idx = train_start_idx + timestampsTrain  # 60*24*5
test_start_idx = val_start_idx + timestampsVal  # 60*24*6

# 加载数据集
train_dataset = DataSetTaxiBJ(datasetType='Train',
                              timestamps=timestampsTrain,
                              window_width=window_width,
                              horizon=horizon,
                              start_idx=train_start_idx)
print('trainDataset is ok....')
train_dataloader = DataLoader(dataset=train_dataset,
                              batch_size=batch_size,
                              shuffle=True,
                              collate_fn=traffNet_collect_fn)
print('trainDataLoader is ok....')

val_dataset = DataSetTaxiBJ(datasetType='Val',
                            timestamps=timestampsVal,
                            window_width=window_width,
                            horizon=horizon,
                            start_idx=val_start_idx)
print('valDataset is ok....')
val_dataloader = DataLoader(dataset=val_dataset,
                            batch_size=batch_size,
                            shuffle=True,
                            collate_fn=traffNet_collect_fn)

# 定义模型，目标函数，优化器
start_epoch = 0
model = PredTraffModel_taxibj(seq_max_len=seq_max_size,
                             window_width=window_width,
                             edge_num=edgeNum,
                             batch_size=batch_size,
                             horizon=horizon,
                             device=device)
model = model.to(device)
print(model)

criterion = torch.nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=lr)

# 加载路径学习预训练参数
weights_path = 'pathSelParams_taxibj.pth'
pre_weights_dict = torch.load(weights_path, map_location=torch.device('cuda:0'))
missing_keys, unexpected_keys = model.load_state_dict(pre_weights_dict, strict=False)
print(f'missing_key:{missing_keys}')
print(f'unexpected_key:{unexpected_keys}')

print(f'batch_size:{batch_size}')
# 开始训练
min_val_total_loss = 10000
for epoch in range(epochs):
    epoch_start_time = time.time()
    # train model......
    train_total_loss = 0
    train_dataloader = tqdm(train_dataloader, file=sys.stdout)

    model.train()
    for i, data in enumerate(train_dataloader):
        torch.cuda.empty_cache()
        optimizer.zero_grad()

        batchGraphSeq = data[0].to(device)
        labels = data[1].to(torch.float32).to(device)
        logits, _, _ = model(batchGraphSeq)

        loss = criterion(logits, labels)

        train_total_loss = train_total_loss + loss.item()

        loss.backward()
        optimizer.step()

    train_loss = train_total_loss / len(train_dataloader)

    # validate model....
    model.eval()

    val_total_loss = 0
    val_dataloader = tqdm(val_dataloader, file=sys.stdout)

    with torch.no_grad():
        for val_data in val_dataloader:
            batchGraphSeq = val_data[0].to(device)
            labels = val_data[1].to(torch.float32).to(device)

            logits, _, _ = model(batchGraphSeq)

            loss = criterion(logits, labels)
            val_total_loss = val_total_loss + loss.item()

    val_loss = val_total_loss / len(val_dataloader)
    epoch_end_time = time.time()
    if not os.path.exists(f'../results/traffNet_taxibj'):
        os.makedirs(f'../results/traffNet_taxibj')
    with open(f'../results/traffNet_taxibj/loss_taxibj.txt', 'a') as f:
        f.write(
            f"[epoch:{(epoch + start_epoch)} | train_total_loss:{train_total_loss},val_total_loss:{val_total_loss} | avgbatchTrainLoss:{train_loss},avgbatchValLoss:{val_loss} | time:{epoch_end_time - epoch_start_time}" + '\n')
    print(
        f"[epoch:{epoch + start_epoch} | train_total_loss:{train_total_loss},val_total_loss:{val_total_loss} | avgbatchTrainLoss:{train_loss},avgbatchValLoss:{val_loss} | time:{epoch_end_time - epoch_start_time}")

    if min_val_total_loss > val_total_loss:
        torch.save(model, f'../results/traffNet_taxibj/model_taxibj.pkl')
        min_val_total_loss = val_total_loss
