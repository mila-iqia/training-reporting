from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import colors
from openpyxl.styles import Font, Color

import json
import os
import glob
from json import JSONEncoder
import pandas as pd
from math import isnan, isinf
import sys


def read_results(report_name):
    str_report = open(report_name, 'r').read().strip()[:-1]
    return json.loads(str_report + ']')


report_folder = f'/home/user1/mlperf/results_1/power9'


def printf(*args, indent=0, **kwargs):
    print(' ' * (indent * 4), *args, **kwargs)


perf_reports = {}
batch_reports = {}


class Accumulator:
    def __init__(self):
        self.values = []

    def append(self, v):
        self.values.append(v)

    def max(self):
        return max(self.values)

    def min(self):
        return min(self.values)

    def sum(self):
        return sum(self.values)

    def __len__(self):
        return len(self.values)

    @property
    def avg(self):
        return self.sum() / len(self)

    def __repr__(self):
        return f'(avg={self.avg}, {len(self)})'


for vendor_name in os.listdir(report_folder):
    printf(f'Processing vendor: {vendor_name}')

    baselines_results = glob.glob(f'{report_folder}/{vendor_name}/baselines_*')

    device_count = len(baselines_results)
    printf(f'Found reports for {device_count} GPUs', indent=1)
    vendor_perf_reports = {}
    vendor_batch_loss_reports = {}

    perf_reports[vendor_name] = vendor_perf_reports
    batch_reports[vendor_name] = vendor_batch_loss_reports

    # we want device 0 to be first since it is the report with the most reports (distributed)
    baselines_results.sort()

    for idx, device_reports in enumerate(baselines_results):
        printf(f'Reading (device_id: {idx}) (report: {device_reports})', indent=2)

        # List of Results for each Trial
        reports = read_results(device_reports)

        for bench_result in reports:
            bench_name = bench_result['name']
            uid = bench_result['unique_id']
            version = bench_result['version']
            unique_id = bench_name  # (uid, bench_name)

            # Select the task that matters
            if bench_name == 'wlm' and bench_result['model'] != 'GRU':
                continue

            if bench_name == 'wlmfp16' and bench_result['model'] != 'GRU':
                continue

            if bench_name == 'loader' and bench_result['batch_size'] != 256:
                continue

            if bench_name == 'toy_lstm' and bench_result['dtype'] != 'float32':
                continue

            if bench_name == 'ssd' and len(bench_result['vcd']) > 1:
                continue

            if bench_name == 'image_loading_loader_pytorch_loaders.py':
                batch_size = bench_result['batch_size']
                unique_id = f'{unique_id}_{batch_size}'
                version = f'{unique_id}_{batch_size}'

            printf(f'Processing {bench_name} {version}', indent=3)

            if unique_id in vendor_perf_reports and idx == 0:
                printf(f'[!] Error two benchmark with the same name (name: {bench_name})', indent=4)
            elif idx == 0:
                perf_report = dict(
                    train_item=Accumulator(),
                    unique_id=uid,
                    version=version,
                    error=[],
                    name=bench_name,
                )
                vendor_perf_reports[unique_id] = perf_report

            elif unique_id not in vendor_perf_reports:
                printf(f'[!] Error missing benchmark for previous GPU (name: {bench_name})', indent=4)
                perf_report = dict(train_item=Accumulator(), unique_id=uid, version=version, error=[])
                vendor_perf_reports[unique_id] = perf_report

            # Accumulate values
            perf_report = vendor_perf_reports[unique_id]
            if perf_report['unique_id'] != uid:
                printf(f'[!] Error unique_ids do not match cannot aggregate (name: {bench_name})!', indent=4)
                perf_report['error'].append('id mismatch')

            elif perf_report['version'] != version:
                printf(f'[!] Error versions do not match cannot aggregate!', indent=4)
                perf_report['error'].append('version mismatch')

            else:
                perf_report['train_item'].append(bench_result['train_item']['avg'])

            batch_loss = bench_result.get('batch_loss')
            if batch_loss is None:
                printf(f'/!\\ No batch loss for benchmark (name: {bench_name})', indent=4)
            else:
                if unique_id not in vendor_batch_loss_reports:
                    vendor_batch_loss_reports[unique_id] = []

                vendor_batch_loss_reports[unique_id].append(batch_loss)


def filer_report(rep):
    new_rep = {}

    for vendor, report in rep.items():
        vendor_rep = {}
        new_rep[vendor] = vendor_rep

        for name, v in report.items():
            key = f'{name}_{v["version"]}_{v["unique_id"]}'
            vendor_rep[key] = v['train_item'].sum()

    return new_rep


weight_table = {
    'atari'                   : (2.88, 26.5405955792167),
    'cart'                    : (2.67, 7302.07868564706),
    'convnet_distributed_fp16': (3.16, 787.612513885864),
    'convnet_distributed'     : (2.97, 679.552350938073),
    'convnet_fp16'            : (2.97, 1679.83933693595),
    'convnet'                 : (2.79, 854.372140032470),
    'dcgan_all'               : (2.97, 309.723619627068),
    'dcgan'                   : (2.79, 953.948799476626),
    'fast_style'              : (2.79, 1012.08893408226),
    'loader'                  : (2.96, 7399.55789895996),
    'recom'                   : (2.81, 74767.2559322286),
    'reso'                    : (2.79, 1177.57382438524),
    'ssd'                     : (2.79, 145.729436411335),
    'toy_lstm'                : (2.67, 4.10197009223690),
    'toy_reg'                 : (2.67, 1234013.49127685),
    'translator'              : (2.78, 900.443830123957),
    'vae'                     : (2.79, 27375.6153865499),
    'wlm'                     : (2.78, 6487.87603739007),
    'wlmfp16'                 : (2.96, 22089.7959228754),
}


import pandas as pd
df = pd.DataFrame(filer_report(perf_reports))
df.loc[:, 'result'] = (df.sum(axis=1) - df.max(axis=1) - df.min(axis=1)) / (df.count(axis=1) - 2)

final_report = {}
total = 0
wtotal = 0

for k, value in df['result'].items():

    for bk, (w, b) in weight_table.items():
        if k.startswith(bk):
            v = value * w / b
            final_report[k] = v
            total += v
            wtotal += w

final_report['total'] = total / wtotal
print(json.dumps(final_report, indent=2))

df.to_csv('report.csv')
