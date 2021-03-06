import os
from datetime import datetime


def process_timestamp(timestamp):
    chop_timestamp = timestamp.split('_')
    list_ts = []
    for i in chop_timestamp[0].split('-'):
        list_ts.append(i)
    for i in chop_timestamp[1].split(':'):
        list_ts.append(i)
    list_ts = [int(y) for y in list_ts]

    start_dt = datetime(list_ts[0], list_ts[1],
                        list_ts[2], list_ts[3], list_ts[4], list_ts[5])

    return start_dt


start = process_timestamp('2021-01-19_17:45:40')
end = process_timestamp('2021-01-19_17:48:00')




# for t in os.listdir('/home/pi/Desktop/Mission'):
#     if start < process_timestamp(t) and process_timestamp(t) < end:
#         #print(os.listdir('/home/pi/Desktop/Mission' + '/' + t))
#         for file in os.listdir('/home/pi/Desktop/Mission' + '/' + t):
#             print('/home/pi/Desktop/Mission' + '/' + t + '/' + file)


def process_downlink_filepaths(start_timestamp, end_timestamp):
    MISSION_ROOT_FILEPATH = '/home/pi/Desktop/Mission'

    list_filepaths = []

    for timestamp in os.listdir('/home/pi/Desktop/Mission'):
        processed_timestamp = process_timestamp(timestamp)
        if start_timestamp < processed_timestamp and processed_timestamp < end_timestamp:
            for file in os.listdir('/home/pi/Desktop/Mission' + '/' + timestamp):
                list_filepaths.append(
                    '/home/pi/Desktop/Mission' + '/' + timestamp + '/' + file)

    return list_filepaths


print(process_downlink_filepaths(start, end))