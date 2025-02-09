#!/usr/bin/python
# Software License Agreement (BSD License)
#
# Copyright (c) 2013, Juergen Sturm, TUM
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of TUM nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Requirements:
# sudo apt-get install python-argparse

"""
Modified and extended by Matthias Mueller - Intel Intelligent Systems Lab - 2020
The controls are event-based and not synchronized to the frames.
This script matches the control signals to frames.
Specifically, if there was no control signal event within some threshold (default: 1ms),
the last control signal before the frame is used.
"""

import os

from . import utils


def read_file_list(filename):
    """
    Reads a trajectory from a text file.

    File format:
    The file format is "stamp d1 d2 d3 ...", where stamp denotes the time stamp (to be matched)
    and "d1 d2 d3.." is arbitary data (e.g., a 3D position and 3D orientation) associated to this timestamp.

    Input:
    filename -- File name

    Output:
    dict -- dictionary of (stamp,data) tuples

    """
    f = open(filename)
    # discard header
    header = f.readline()
    data = f.read()
    lines = data.replace(",", " ").replace("\t", " ").split("\n")
    data = [
        [v.strip() for v in line.split(" ") if v.strip() != ""]
        for line in lines
        if len(line) > 0 and line[0] != "#"
    ]
    data = [(int(line[0]), line[1:]) for line in data if len(line) > 1]
    return dict(data)


def associate(first_list, second_list, max_offset):
    """
    Associate two dictionaries of (stamp,data). As the time stamps never match exactly, we aim
    to find the closest match for every input tuple.

    Input:
    first_list -- first dictionary of (stamp,data) tuples
    second_list -- second dictionary of (stamp,data) tuples
    offset -- time offset between both dictionaries (e.g., to model the delay between the sensors)
    max_difference -- search radius for candidate generation

    Output:
    matches -- list of matched tuples ((stamp1,data1),(stamp2,data2))

    """
    first_keys = list(first_list)
    second_keys = list(second_list)
    potential_matches = [
        (b - a, a, b) for a in first_keys for b in second_keys if (b - a) < max_offset
    ]  # Control before image or within max_offset
    potential_matches.sort(reverse=True)
    matches = []
    for diff, a, b in potential_matches:
        if a in first_keys and b in second_keys:
            first_keys.remove(a)  # Remove frame that was assigned
            matches.append((a, b))  # Append tuple

    matches.sort()
    return matches


def match_frame_ctrl_input(
    data_dir,
    datasets,
    max_offset,
    redo_matching=False,
    remove_zeros=True,
    policy="autopilot",
):
    frames = []
    for dataset in datasets:
        for folder in utils.list_dirs(os.path.join(data_dir, dataset)):
            session_dir = os.path.join(data_dir, dataset, folder)
            frame_list = match_frame_session(
                session_dir, max_offset, redo_matching, remove_zeros, policy
            )
            for timestamp in list(frame_list):
                frames.append(frame_list[timestamp][0])
    return frames


def match_frame_session(
    session_dir, max_offset, redo_matching=False, remove_zeros=True, policy="autopilot"
):

    if policy == "autopilot":
        matched_frames_file_name = "matched_frame_ctrl_cmd.txt"
        processed_frames_file_name = "matched_frame_ctrl_cmd_processed.txt"
        log_file = "indicatorLog.txt"
        csv_label_string = "timestamp (frame),time_offset (cmd-frame),time_offset (ctrl-frame),frame,left,right,cmd\n"
        csv_label_string_processed = "timestamp,frame,left,right,cmd\n"
    elif policy == "point_goal_nav":
        matched_frames_file_name = "matched_frame_ctrl_goal.txt"
        processed_frames_file_name = "matched_frame_ctrl_goal_processed.txt"
        log_file = "goalLog.txt"
        csv_label_string = "timestamp (frame),time_offset (goal-frame),time_offset (ctrl-frame),frame,left,right,dist,sinYaw,cosYaw\n"
        csv_label_string_processed = "timestamp,frame,left,right,dist,sinYaw,cosYaw\n"
    else:
        raise Exception("Unknown policy")

    sensor_path = os.path.join(session_dir, "sensor_data")
    img_path = os.path.join(session_dir, "images")
    print("Processing folder %s" % (session_dir))
    if not redo_matching and os.path.isfile(
        os.path.join(sensor_path, "matched_frame_ctrl.txt")
    ):
        print(" Frames and controls already matched.")
    else:
        # Match frames with control signals
        frame_list = read_file_list(os.path.join(sensor_path, "rgbFrames.txt"))
        if len(frame_list) == 0:
            raise Exception("Empty rgbFrames.txt")
        ctrl_list = read_file_list(os.path.join(sensor_path, "ctrlLog.txt"))
        if len(ctrl_list) == 0:
            raise Exception("Empty ctrlLog.txt")
        matches = associate(frame_list, ctrl_list, max_offset)
        with open(os.path.join(sensor_path, "matched_frame_ctrl.txt"), "w") as f:
            f.write("timestamp (frame),time_offset (ctrl-frame),frame,left,right\n")
            for a, b in matches:
                f.write(
                    "%d,%d,%s,%s\n"
                    % (
                        a,
                        b - a,
                        ",".join(frame_list[a]),
                        ",".join(ctrl_list[b]),
                    )
                )
        print(" Frames and controls matched.")

    if not redo_matching and os.path.isfile(
        os.path.join(sensor_path, matched_frames_file_name)
    ):
        print(" Frames and commands already matched.")
    else:
        # Match frames and controls with indicator commands
        frame_list = read_file_list(os.path.join(sensor_path, "matched_frame_ctrl.txt"))
        if len(frame_list) == 0:
            raise Exception("Empty matched_frame_ctrl.txt")
        cmd_list = read_file_list(os.path.join(sensor_path, log_file))

        if policy == "autopilot":
            # Set indicator signal to 0 for initial frames
            if len(cmd_list) == 0 or sorted(frame_list)[0] < sorted(cmd_list)[0]:
                cmd_list[sorted(frame_list)[0]] = ["0"]

        elif policy == "point_goal_nav":
            if len(cmd_list) == 0:
                raise Exception("Empty goalLog.txt")

        matches = associate(frame_list, cmd_list, max_offset)
        with open(os.path.join(sensor_path, matched_frames_file_name), "w") as f:
            f.write(csv_label_string)
            for a, b in matches:
                f.write(
                    "%d,%d,%s,%s\n"
                    % (a, b - a, ",".join(frame_list[a]), ",".join(cmd_list[b]))
                )
        print(" Frames and high-level commands matched.")

    if not redo_matching and os.path.isfile(
        os.path.join(sensor_path, processed_frames_file_name)
    ):
        print(" Preprocessing already completed.")
    else:
        # Cleanup: Add path and remove frames where vehicle was stationary
        frame_list = read_file_list(os.path.join(sensor_path, matched_frames_file_name))
        with open(os.path.join(sensor_path, processed_frames_file_name), "w") as f:
            f.write(csv_label_string_processed)
            # max_ctrl = get_max_ctrl(frame_list)
            for timestamp in list(frame_list):
                frame = frame_list[timestamp]
                if len(frame) < 6:
                    continue

                if policy == "autopilot":
                    left = int(frame[3])
                    right = int(frame[4])
                    # left = normalize(max_ctrl, frame[3])
                    # right = normalize(max_ctrl, frame[4])
                    if remove_zeros and left == 0 and right == 0:
                        print(f" Removed timestamp: {timestamp}")
                        del frame
                    else:
                        frame_name = os.path.join(img_path, frame[2] + "_crop.jpeg")
                        cmd = int(frame[5])
                        f.write(
                            "%s,%s,%d,%d,%d\n"
                            % (timestamp, frame_name, left, right, cmd)
                        )

                elif policy == "point_goal_nav":
                    left = float(frame_list[timestamp][3])
                    right = float(frame_list[timestamp][4])
                    if remove_zeros and left == 0.0 and right == 0.0:
                        print(" Removed timestamp:%s" % (timestamp))
                        del frame_list[timestamp]
                    else:
                        frame_name = os.path.join(
                            img_path, frame_list[timestamp][2] + ".jpeg"
                        )
                        dist = float(frame_list[timestamp][5])
                        sinYaw = float(frame_list[timestamp][6])
                        cosYaw = float(frame_list[timestamp][7])
                        f.write(
                            "%s,%s,%f,%f,%f,%f,%f\n"
                            % (timestamp, frame_name, left, right, dist, sinYaw, cosYaw)
                        )

        print(" Preprocessing completed.")

    return read_file_list(os.path.join(sensor_path, processed_frames_file_name))


def normalize(max_ctrl, val):
    return int(int(val) / max_ctrl * 255)


def get_max_ctrl(frame_list):
    max_val = 0
    for timestamp in list(frame_list):
        frame = frame_list[timestamp]
        if len(frame) < 6:
            continue
        left = int(frame[3])
        right = int(frame[4])
        max_val = max(max_val, abs(left), abs(right))
    if max_val == 0:
        max_val = 255
    return max_val
