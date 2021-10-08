#!/usr/bin/env python
# coding: utf-8

# # Automatic video cutter

import os
import sys
import time
import wave
import json

import moviepy.editor as mp
from vosk import Model, KaldiRecognizer, SetLogLevel

# custom import
import Word as custom_Word


def recognize_audio_vosk(audio_path, model):
    '''
    Recognize audio using vosk model.
    Language of the recognition depends on model.
    Returns list of Word objects. Each of them has the following attributes:
        conf (float): degree of confidence, from 0 to 1
        end (float): end time of the pronouncing the word, in seconds
        start (float): start time of the pronouncing the word, in seconds
        word (str): recognized word

    Parameters:
        audio_path (str): path to the audio file to recognize. Must be WAV format mono PCM
        model: vosk model. Must be loaded with `model = Model(model_path)` command

    Returns:
        list_of_Words (array): list of Word objects
    '''

    # check if audio is mono wav
    wf = wave.open(audio_path, "rb")
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
        print("Audio file must be WAV format mono PCM")
        sys.exit()

    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)

    print('\n\tStarting to convert audio to text. It may take some time...')
    start_time = time.time()

    results = []
    # recognize speech using vosk model
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            part_result = json.loads(rec.Result())
            results.append(part_result)

    part_result = json.loads(rec.FinalResult())
    results.append(part_result)

    # convert list of JSON dictionaries to list of 'Word' objects
    list_of_Words = []
    for sentence in results:
        if len(sentence) == 1:
            # sometimes there are bugs in recognition
            # and it returns an empty dictionary
            # {'text': ''}
            continue
        for obj in sentence['result']:
            w = custom_Word.Word(obj)  # create custom Word object
            list_of_Words.append(w)  # and add it to list

    # forming a final string from the words
    text = ''
    for w in list_of_Words:
        text += w.word + ' '

    time_elapsed = time.strftime('%H:%M:%S',
                                 time.gmtime(time.time() - start_time))
    print(f'Done! Elapsed time = {time_elapsed}')

    print("\n\tVosk thinks you said:\n")
    print(text)

    wf.close  # close audiofile

    return list_of_Words


def segments_from_audio_control_words(list_of_Words, start_word='начало', end_word='конец', offset=0.5):
    '''
    Parse list of Word objects for 'start_word' and 'end_word' 
    and returns 'segments' - list of tuples, where each turple is
    (start_time of start_word - offset, end_time of end_word + offset)

    Parameters:
        list_of_Words (array): list of Word objects. 
                               Received from `recognize_audio_vosk()` function
        start_word (str): control word that signals the beginning of the video fragment to be cut
        end_word (str): control word that signals the ending of the video fragment to be cut
        offset (float): offset in seconds. Number being subtracted from 'start_time' for 'start_word' 
                        and added to 'end_time' for 'end_word'

    Returns:
        segments (array): list of tuples (start_time, end_time)
    '''

    print("\n\tStarting the search for control words...")

    # lists for start and end times
    starts = []
    ends = []

    # cycle by all Words
    for w in list_of_Words:
        if w.word == start_word:
            starts.append(w.start - offset)
        if w.word == end_word:
            ends.append(w.end + offset)

    # from starts and ends to segments
    # starts = [1, 3], ends = [2, 4] ->
    # segments = (0, 1), (2, 3), (4, None)

    segments = []
    length = max(len(starts), len(ends))
    for i in range(length + 1):
        if i == 0:
            segments.append((0, starts[0]))
        elif i == length:
            segments.append((ends[i-1], None))
        else:
            # intermediate values
            segments.append((ends[i-1], starts[i]))
    print("The search of control words is completed. Got the following array of segments: \n")
    print(segments)

    return segments


def segments_from_audio_silence(list_of_Words, threshold=2, offset=1):
    '''
    Parse list of Word objects for silence.
    If silence lasts longer than treshold value, this fragment will be cut.
    Returns 'segments' - list of tuples, where each turple is
    (start_time, end_time)

    Parameters:
        list_of_Words (array): list of Word objects. 
                               Received from `recognize_audio_vosk()` function
        threshold (float): treshold value in seconds
        offset (float): offset in seconds. Number being subtracted from 'start_time' for 'start_word' 
                        and added to 'end_time' for 'end_word'

    Returns:
        segments (array): list of tuples (start_time, end_time)
    '''

    print("\n\tStarting the search for silence...")

    # lists for start and end times
    starts = []
    ends = []

    for i in range(len(list_of_Words) - 1):
        current_word = list_of_Words[i]
        next_word = list_of_Words[i+1]
        if next_word.start - current_word.end > threshold:
            # find moment of silence
            starts.append(current_word.end + offset)
            ends.append(next_word.start - offset)

    # from starts and ends to segments
    # starts = [1, 3], ends = [2, 4] ->
    # segments = (0, 1), (2, 3), (4, None)

    segments = []
    length = max(len(starts), len(ends))
    for i in range(length + 1):
        if i == 0:
            segments.append((0, starts[0]))
        elif i == length:
            segments.append((ends[i-1], None))
        else:
            # intermediate values
            segments.append((ends[i-1], starts[i]))
    print("The search of silence is completed. Got the following array of segments: \n")
    print(segments)

    return segments


def crop_video_by_segments(video, segments, result_path, bitrate=None) -> None:
    '''
    Crop video according to 'segments' list and
    save final video to 'result_path'.

    Parameters:
        video: moviepy.editor.VideoFileClip object
        segments (array): list of tuples (start_time, end_time).
                          Received from `segments_from_audio_*()` functions
        result_path (str): path to save final video
        bitrate (str): bitrate for write_videofile function. 
               Default is None, must be like '2500k', '5000k', '10000k', etc.
    '''

    print("\n\tStarting the video processing...")

    clips = []  # list of all video fragments
    for start_seconds, end_seconds in segments:
        # crop a video clip and add it to list
        c = video.subclip(start_seconds, end_seconds)
        clips.append(c)

    final_clip = mp.concatenate_videoclips(clips)
    final_clip.write_videofile(result_path, bitrate=bitrate)
    final_clip.close()

    print("The video processing is completed")


def main(model_path='', video_path='', result_path='', silence=True,
         threshold=1, offset_silence=0.25, start_word='начало', end_word='конец', offset_words=0.5, bitrate=None):
    '''
    The main method of the program.
    Process 'video_path' video file. Convert video to audio, recognize audio to text using 'model_path' vosk model.
    If silence == True, cut off silence moments > 'threshold'.  
    If silence == False, process according to control words - 'start_word' and 'end_word'.
    Save processed video to 'result_path'.

    Parameters:
        model_path (str): path to vosk model downloaded from https://alphacephei.com/vosk/models
        video_path (str): path to video file to convert
        result_path (str): new filename to save final video
        silence (bool): processing method. If True, process video with silence mode, if False - with control words

        threshold (float): threshold of silence time in seconds. Used only if silence==True
        offset_silence (float): offset in seconds. Used only if silence==True

        start_word (str): control word that signals the beginning of the video fragment to be cut.
                          Used only if silence==False
        end_word (str): control word that signals the ending of the video fragment to be cut.
                        Used only if silence==False
        offset_words (float): offset in seconds. Used only if silence==False
        bitrate (str): bitrate for write_videofile function. 
                       Default is None, must be like '2500k', '5000k', '10000k' etc.

    Returns:
        None
    '''

    # Loading a vosk model
    if not os.path.exists(model_path):
        print("Please download the model from" +
              f"https://alphacephei.com/vosk/models and unpack as {model_path}")
        sys.exit()

    print(f"Reading your vosk model '{model_path}'...")
    model = Model(model_path)
    print(f"'{model_path}' model was successfully read")

    # temporary filename for audiofile (will be deleted)
    audio_path = video_path[:-3] + "wav"

    # Read video and convert it to mono audio
    # if videofile exists
    if not os.path.exists(video_path):
        print(f"File {video_path} doesn't exist")
        sys.exit()

    # read video
    clip = mp.VideoFileClip(video_path)

    # convert video to audio
    # ffmpeg_params=["-ac", "1"] parameter convert audio to mono format
    clip.audio.write_audiofile(audio_path, ffmpeg_params=["-ac", "1"])

    # Speech Recognition with vosk model
    list_of_Words = recognize_audio_vosk(audio_path=audio_path,
                                         model=model)

    # delete audio
    try:
        os.remove(audio_path)
    except PermissionError:
        print(
            f"The file {audio_path} cannot be deleted - it is used by another process")

    # Search for timestamps
    if silence:
        segments = segments_from_audio_silence(list_of_Words,
                                               threshold=threshold,
                                               offset=offset_silence)
    else:
        segments = segments_from_audio_control_words(list_of_Words,
                                                     start_word=start_word,
                                                     end_word=end_word,
                                                     offset=offset_words)

    # Video Processing
    crop_video_by_segments(video=clip,
                           segments=segments,
                           result_path=result_path,
                           bitrate=bitrate)


if __name__ == '__main__':

    # Set parameters

    # path to vosk model downloaded from https://alphacephei.com/vosk/models
    model_path = "models/vosk-model-en-us-0.21"
    # path to video file to convert
    video_path = "videos/video_silence.mp4"
    # new filename to save final video
    result_path = video_path[:-4] + "_processed.mp4"

    silence = True  # processing method
    # if True, process video with silence
    # if False - with control words
    
    # bitrate for write_videofile function. 
    # Default is None, must be like '2500k', '5000k', '10000k' etc.
    bitrate = None 

    # Next two parameters are used only if silence==True

    # threshold of silence time in seconds
    threshold = 1
    # offset in seconds
    offset_silence = 0.25

    # Next three parameters are used only if silence==False

    # control word that signals the beginning of the video fragment to be cut
    start_word = 'начало'
    # control word that signals the ending of the video fragment to be cut
    end_word = 'конец'
    # offset in seconds
    offset_words = 0.5

    main(model_path=model_path, video_path=video_path, result_path=result_path,
         silence=silence, threshold=threshold, offset_silence=offset_silence,
         start_word=start_word, end_word=end_word, offset_words=offset_words, 
         bitrate=bitrate)
