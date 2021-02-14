from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from picamera import PiCamera
import time
import subprocess
import os
import serial

done = False

#### DOWNLINK CONSTANTS ####
CHUNK_SIZE = 168
BATCH_SIZE = 300
TIME_SLEEP_AFTER_START = 0.09
TIME_SLEEP_AFTER_END = 1.5
TIME_LONG_DELAY = 0.046
TIME_SHORT_DELAY = 0.028

TELEMETRY_PACKET_TYPE_DOWNLINK_START = 30
TELEMETRY_PACKET_TYPE_DOWNLINK_PACKET = 31

packet_count = 0
#### ------------------ ####

MISSION_ROOT_FILEPATH = '/home/pi/Desktop/Mission'


def main():

    # Initialize Scheduler in background
    scheduler = BackgroundScheduler()

    # Initialize Camera
    camera_obj = PiCamera()

    # Start the scheduler
    scheduler.start()

    # Open Serial port to receive commands
    # Blocking to wait forever for input
    ser_cmd_input = serial.Serial('/dev/serial0', baudrate=9600, timeout=None)

    # Open Serial port to downlink images
    ser_downlink = serial.Serial("/dev/ttyUSB0", baudrate=115200, timeout=10)

    while True:
        try:
            # Format: cmd 2020-10-18_16:33:57 5 1000
            data_read = ser_cmd_input.readline().decode("utf-8").replace("\r\n", "")
            #data_read = b'downlink 2021-02-14_22:58:00 2021-01-19_17:45:40 2021-01-19_17:47:40'.decode("utf-8").replace("\r\n", "")

            list_data_read = data_read.split(" ")
            
            print(list_data_read)

            cmd = list_data_read[0]

            if cmd == 'mission':
                timestamp_start, num, list_ts_image = process_mission_command(
                    list_data_read)

                # Create folder path part applicable for mission only
                # Create Folder for mission
                storage_path = MISSION_ROOT_FILEPATH
                mission_folder_path = storage_path + '/' + timestamp_start.replace(" ", "_")
                os.mkdir(mission_folder_path)
                print("Mission directory created: %s" % mission_folder_path)

                count = 0
                for ts in list_ts_image:
                    count = count + 1
                    scheduler.add_job(mission_cmd, next_run_time=timestamp_start, args=[
                                      camera_obj, mission_folder_path, timestamp_start, count, num])

            if cmd == 'downlink':
                # Process all 3 timestamps
                timestamp_start_downlink = process_timestamp(list_data_read[1])
                timestamp_query_start = process_timestamp(list_data_read[2])
                timestamp_query_end = process_timestamp(list_data_read[3])

                print()

                # Obtain list of filepaths to images to downlink
                filepath_list = process_downlink_filepaths(
                    timestamp_query_start, timestamp_query_end)

                scheduler.add_job(download_cmd, next_run_time=timestamp_start_downlink, args=[
                                  ser_downlink, filepath_list])
                
            while True:
                pass

        except KeyboardInterrupt:
            print("End, exiting")
            scheduler.shutdown()
            camera_obj.close()
            exit()

        except UnicodeDecodeError:
            print()
            print("Error -- unicode decode error")
            print("Did not manage to read command")
            print()

        # Fall through exception -- just in case
#         except Exception as ex:
#             print(ex)


def process_mission_command(data_read_list):

    # Function processes the list of parsed timestamps to add job for
    def create_list_ts(dt, num, interval):
        # Function to parse timestamp
        ls = [dt]
        curr_dt = dt
        for n in range(num-1):
            ls.append(curr_dt + timedelta(milliseconds=interval))
            curr_dt = curr_dt + timedelta(milliseconds=interval)
        return ls

    cmd = data_read_list[0]
    timestamp_start = data_read_list[1]
    num = int(data_read_list[2])
    interval = int(data_read_list[3])

    print("Command: %s" % cmd)
    print("Timestamp: %s" % timestamp_start)
    print("Images to take: %s" % num)
    print("Interval (ms): %s" % interval)

    # Parse timestamp into datetime format
    start_dt = process_timestamp(timestamp_start)

    list_ts_image = create_list_ts(start_dt, num, interval)

    return timestamp_start, num, list_ts_image


def mission_cmd(camera_obj, mission_folder_path, timestamp, count, num):

    # Function takes a single image
    # Saves the image with a given name
    # To be used in the scheduled job
    def take_image(camera_obj, mission_folder_path, timestamp, count):
        name_image = mission_folder_path + '/' + \
            str(timestamp) + "_" + str(count) + '.jpg'

        # placeholder name to allow windows to store
        # name_image = mission_folder_path + '/'+ str(count) +'.jpg'

        camera_obj.capture(name_image)
        print(f'Image at {name_image} taken at {datetime.utcnow()}')

    global done
    take_image(camera_obj, mission_folder_path, timestamp, count)
    if count == num:
        done = True


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


#### DOWNLINK FUNCTIONS ####

def process_downlink_command(data_read_list):
    timestamp_downlink = process_timestamp(data_read_list[1])
    timestamp_query_start = process_timestamp(data_read_list[2])
    timestamp_query_end = process_timestamp(data_read_list[3])
    return [timestamp_downlink, timestamp_query_start, timestamp_query_end]


# Receive timestamp in plaintext
def process_downlink_filepaths(start_timestamp, end_timestamp):
    list_filepaths = []
    
    list_dir_mission = os.listdir(MISSION_ROOT_FILEPATH)

    for mission_timestamp in list_dir_mission:
        
        processed_timestamp = process_timestamp(mission_timestamp)
        
        if start_timestamp < processed_timestamp and processed_timestamp < end_timestamp:
            
            for file in os.listdir(MISSION_ROOT_FILEPATH + '/' + mission_timestamp):
                
                list_filepaths.append(
                    MISSION_ROOT_FILEPATH + '/' + mission_timestamp + '/' + file)

    return list_filepaths


def download_cmd(ser_obj, filepath_list):
    print(filepath_list)

    for file in filepath_list:

        # Call bash script to execute prep script
        # base64 + gzip
        prep_filepath = './prep_test.sh ' + file
        subprocess.call(prep_filepath, stdout=subprocess.DEVNULL, shell=True)

        # Open and read in the image
        with open('base_enc.gz', 'rb') as file:
            compressed_enc = file.read()
            file.close()
        total_bytes_retrieved = len(compressed_enc)

        # Call bash script to remove currently created compressed files
        subprocess.call('./cleanup.sh base_enc.gz',
                        stdout=subprocess.DEVNULL, shell=True)

        # Process the bytes into batches of chunks to be sent out
        chunk_list = chop_bytes(compressed_enc, CHUNK_SIZE)
        total_chunks = len(chunk_list)

        # Split chunks into batch according to a batch size
        batch_list = split_batch(chunk_list, BATCH_SIZE)
        total_batch = len(batch_list)

        # Send start packet
        start_packet = ccsds_create_downlink_start_packet(
            TELEMETRY_PACKET_TYPE_DOWNLINK_START, total_bytes_retrieved, total_chunks, total_batch)
        ser_obj.write(start_packet)
        time.sleep(TIME_SLEEP_AFTER_START)

        # Begin Batch send of chunk
        current_batch = 1
        for batch in batch_list:
            print(f"BEGIN SEND: BATCH {current_batch}")
            current_batch = current_batch + 1

            # Begin batch send
            batch_send(ser_obj, batch, TIME_SHORT_DELAY, TIME_LONG_DELAY,
                       total_bytes_retrieved, total_chunks, total_batch, current_batch)

            print()

        # Pause before next image send
        time.sleep(15)

#####


# Create a CCSDS Packet Header
# Given source data length
def ccsds_create_packet_header(source_data_len):
    # Contains the Version number, Packet identification,
    # Packet Sequence Control and Packet data length

    global packet_count

    # Abstract header as 6 bytes
    header = bytearray(0)  # octet 1, 2, ..., 6

    octet = 0b0

    # Version number
    octet = octet << 3 | 0b000

    # # Packet identification
    # # @Type indicator -- Set to 0 to indicate telemetry packet
    octet = octet << 1 | 0b0

    # # @Packet Secondary Header Flag -- Set to 0 to indicate that secondary header not present
    octet = octet << 1 | 0b0

    # # @Application Process ID
    # # Defines the process onboard that is sending the packet --> TBC
    octet = octet << 11 | 0b10

    header = header + octet.to_bytes(2, 'big')

    octet = 0b0

    # # Packet Sequence Control
    # # @Grouping packets -- No grouping so set to 0
    octet = octet << 2 | 0b11

    # # @Source Sequence Count
    # # Sequence number of packet modulo 16384
    octet = octet << 14 | packet_count
    packet_count = packet_count + 1

    header = header + octet.to_bytes(2, 'big')

    octet = 0b0

    # # Packet Data Length
    # In terms of octets
    # Total number of octets in packet data field - 1
    octet = octet << 16 | (source_data_len - 1)

    header = header + octet.to_bytes(2, 'big')

    return header


# Function to create a start packet for downlink
# Format: | CCSDS Primary header | Telemetry Packet Type | Total Bytes | Total Chunks to send |
def ccsds_create_downlink_start_packet(telemetry_packet_type, total_bytes, total_chunks, total_batch):

    TOTAL_BYTES_LENGTH = 3  # Bytes
    TOTAL_CHUNKS_LENGTH = 3
    TOTAL_BATCH_LENGTH = 3
    TELEMETRY_TYPE_LENGTH = 1

    # Packet
    packet = bytearray(0)

    # Compute Source data length and create header
    source_data_len = TOTAL_BYTES_LENGTH + \
        TOTAL_CHUNKS_LENGTH + TELEMETRY_TYPE_LENGTH
    ccsds_header = ccsds_create_packet_header(source_data_len)

    packet = packet + ccsds_header

    # Append bytes to packet
    packet = packet + \
        telemetry_packet_type.to_bytes(TELEMETRY_TYPE_LENGTH, 'big')

    packet = packet + total_bytes.to_bytes(TOTAL_BYTES_LENGTH, 'big')

    packet = packet + total_chunks.to_bytes(TOTAL_CHUNKS_LENGTH, 'big')

    packet = packet + total_batch.to_bytes(TOTAL_BATCH_LENGTH, 'big')

    return packet


# Function to create a chunk packet for downlink
# NOTE: Payload length should be a fixed constant (refer to top constants declared)
def ccsds_create_downlink_chunk_packet(telemetry_packet_type, total_bytes, total_chunks, total_batch, current_batch, current_chunk, payload):

    TOTAL_BYTES_LENGTH = 3  # Bytes
    TOTAL_CHUNKS_LENGTH = 3
    TOTAL_BATCH_LENGTH = 3
    CURRENT_CHUNKS_LENGTH = 3
    CURRENT_BATCH_LENGTH = 3

    TELEMETRY_TYPE_LENGTH = 1

    # Packet
    packet = bytearray(0)

    # Compute Source data length and create header
    source_data_len = TOTAL_BYTES_LENGTH + \
        TOTAL_CHUNKS_LENGTH + TELEMETRY_TYPE_LENGTH + \
        CURRENT_CHUNKS_LENGTH + len(payload)
    ccsds_header = ccsds_create_packet_header(source_data_len)

    packet = packet + ccsds_header

    # Append bytes to packet
    packet = packet + \
        telemetry_packet_type.to_bytes(TELEMETRY_TYPE_LENGTH, 'big')

    packet = packet + total_bytes.to_bytes(TOTAL_BYTES_LENGTH, 'big')

    packet = packet + total_chunks.to_bytes(TOTAL_CHUNKS_LENGTH, 'big')

    packet = packet + total_batch.to_bytes(TOTAL_BATCH_LENGTH, 'big')

    packet = packet + current_batch.to_bytes(CURRENT_BATCH_LENGTH, 'big')

    packet = packet + current_chunk.to_bytes(CURRENT_CHUNKS_LENGTH, 'big')

    # Append payload bytes into packet
    packet = packet + payload

    return packet


# Function to initiate a batch tx
def batch_send(serial_obj, batch_arr, short_delay, long_delay, total_bytes_retrieved, total_chunks, total_batch, current_batch):

    # Initiate downlink of chunk packets in the batch
    chunk_counter = 0
    while chunk_counter < len(batch_arr):

        # Create CCSDS packet
        packet = ccsds_create_downlink_chunk_packet(
            TELEMETRY_PACKET_TYPE_DOWNLINK_PACKET, total_bytes_retrieved, total_chunks, total_batch, current_batch, chunk_counter, batch_arr[chunk_counter])

        print(f"Sending {chunk_counter+1} of length {len(packet)}")
        serial_obj.write(packet)

        if chunk_counter % 100 == 0:
            time.sleep(long_delay)
        else:
            time.sleep(short_delay)
        chunk_counter = chunk_counter + 1

    time.sleep(TIME_SLEEP_AFTER_END)


# Returns an array of chunks of bytes, given chunk size and bytes array
def chop_bytes(bytes_arr, chunk_size):
    chunk_arr = []
    idx = 0

    while idx + chunk_size < len(bytes_arr):
        chunk_arr.append(bytes_arr[idx:idx + chunk_size])
        idx = idx + chunk_size

    # Remaining odd sized chunk
    chunk_arr.append(bytes_arr[idx:])

    return chunk_arr


# Given an array of chunks, split them into array of batches given a batch size
def split_batch(chunks_arr, batch_size):
    batch_arr = []
    idx = 0

    while idx + batch_size <= len(chunks_arr):
        batch_arr.append(chunks_arr[idx:idx + batch_size])
        idx = idx + batch_size

    # Remaining odd sized chunk
    batch_arr.append(chunks_arr[idx:])

    return batch_arr


if __name__ == "__main__":
    main()