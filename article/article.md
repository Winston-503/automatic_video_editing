# Automatic Video Editing
## How to implement automatic video editing using Python, moviepy and vosk

Video editing is always tedious. Removing unnecessary video fragments is not a difficult task, but a long one. You need to review the video completely (and possibly more than once!), select all fragments you need, join them and then render the video for a long time. It usually takes more than three hours to simply edit an hour-long video! That's why I came up with this idea.

Of course, alternatives exist. For example, [wisecat](https://www.wisecat.video/), which can do much more than cropping the video. But I want to make a fast, simple, and free program. Python libraries [moviepy](https://zulko.github.io/moviepy/) and [vosk](https://alphacephei.com/vosk/) will help me with this.

## Problem Statement

I want to build a program that will automatically cut some video fragments and then join these fragments together. It has to receive data about these fragments in two ways:
- Automated (partially automatic, with some human intervention) - with recognizing control words, and
- Automatic (completely automatic, without human intervention) - with identifying long moments of silence

| ![video_editing.JPG](./img/video_editing.JPG) |
|:--:|
| <b>Two approaches to video editing. Image by Author</b>|

The task can be divided into the following subtasks:
1. Learn how to edit videos using moviepy
2. Recognize control words/silence and their timestamps
3. Put it all together

## Video Editing with Moviepy

First, let's just try to cut and join the video using the *moviepy* library.

It is very easy - after reading the source video into a `VideoFileClip` object we can do a lot of things with built methods. We will need the following ones:
- `video.subclip(start_seconds, end_seconds)` which returns video fragment, cut from `video` from `start_seconds` to `end_seconds`
- and `concatenate_videoclips(clips)` which put together all video fragments from `clips` list.

Put the list of all `(start_seconds, end_seconds)` pairs you need in the `segments` variable. Now you can use the following code to produce a video from its fragments.

```python
import moviepy.editor as mp

video = mp.VideoFileClip("my_video.mp4")

# delete video fragment from 00:30 to 01:00
segments = [(0, 30),
            (60, None)]

clips = [] # list of all video fragments
for start_seconds, end_seconds in segments:
    # crop a video clip and add it to list
    c = video.subclip(start_seconds, end_seconds)
    clips.append(c)

final_clip = mp.concatenate_videoclips(clips)
final_clip.write_videofile("my_new_video.mp4")
```

In fact, this simple program can already be very useful. It copes well with simple tasks (trim the beginning/end of the video, cut the desired fragment), and works much faster than professional video editing programs (Sony Vegas, etc).

Now, all we have to do is to get these pairs (`segments`) from an intelligent system.

## A Brief Overview of Speech Recognition with Timestamps

This task is more complicated. As a result of searching and experimenting, I decided to use the [vosk API](https://alphacephei.com/vosk/). A detailed tutorial on how to implement speech recognition with timestamps with this library you can find in [this article](https://towardsdatascience.com/speech-recognition-with-timestamps-934ede4234b2). But I will try to briefly describe the most important points here too.

First of all, we need to recognize speech using the vosk model. As I explained in the article above, the vosk speech recognition model outputs a list of JSON dictionaries, that contains four parameters for each recognized word - `confidence`, `start time`, `end time` and recognized `word`. I created a custom `Word` class, that describes words according to this format. The following code recognized `audio_filename` file and outputs a list of `Word` objects. 

```python
import wave
import json

from vosk import Model, KaldiRecognizer, SetLogLevel
import Word as custom_Word

model_path = "models/vosk-model-en-us-0.21"
audio_filename = "audio/speech_recognition_systems.wav"

model = Model(model_path)
wf = wave.open(audio_filename, "rb")
rec = KaldiRecognizer(model, wf.getframerate())
rec.SetWords(True)

# get the list of JSON dictionaries
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
        
# output to the screen
for word in list_of_words:
    print(word.to_string())
```

## Recognize Control Words

Now we know the time of pronouncing each word. There is room for creativity because we need to choose control words. We need two - for the start and the end of the cut fragment.

You can't just use *start* and *stop*. In fact, of course, you can, but you can't be sure that you won't say these words in your usual speech. And in this case, the program will work incorrectly. Initially, I decided to use some rare English words like *sagacious* and *egregious*. But it turned out that rare words are worse recognized, and very rare ones may not be in the dictionary at all. Also at this moment, I realized how much the accent affects speech recognition quality.  Because I'm not a native English speaker, I decided to move on to a simpler solution.

I decided to just use the words *start* and *end* in my native language. Since vosk has foreign models, you can recognize the speech with your native language model. The text will be recognized as nonsense, but we don't need it, right? The main thing is that the *control words* will be recognized. In Russian, they are written as **начало** and **конец**, and pronounced like **nachalo** and **konets**, respectively. The first word indicates the beginning of the fragment to be cut, and the second - its end.

| ![english_speech_russian_model.jpg](./img/english_speech_russian_model.jpg) |
|:--:|
| <b>Example of English speech recognition with a Russian model. Image by Author</b>|

It is possible to recognize *combinations of English words* as control commands. You can go even further and recognize sounds - for example, finger clicks or clapping. However, it seemed less convenient to me.

Now we need to iterate through the `list_of_words` and check whether the recognized word is one of the control words. If yes, then we remember the time (start time for start_word and end time for end_word). I also created the `offset` variable to be sure that the cropping of the video is not too sharp.

```python
# list_of_Words received earlier

start_word = "начало"
end_word = "конец"
offset = 0.5  # seconds

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
```

After that, all that remains is to pass the `segments` variable to the code snippet in **Video Editing with Moviepy** section!

## Recognize Silence

Another option is to cut out the moments when silence lasts longer than a certain threshold (for example 2 seconds). Almost everything here is already familiar to us, you can see the code below.

```python
# list_of_Words received earlier

threshold = 2  # in seconds
# if silence lasts longer than treshold value, 
# this fragment will be cut

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
```

This approach is fully automated and does not require any human intervention during or after video recording. You just specify the path to the video and get the video without silent moments.

## Put it all together

The two main components of the program are ready to use, we need only to connect them. The only moment that was not described is the conversion of video to mono audio. But *moviepy* can easily cope with this.

```python
import moviepy.editor as mp

clip = mp.VideoFileClip("video.mp4")
# convert video to audio
# ffmpeg_params=["-ac", "1"] parameter convert audio to mono format
clip.audio.write_audiofile("audio.wav", ffmpeg_params=["-ac", "1"])
```

### Project Structure

The full program with detailed comments is available in [this GitLab repo](https://gitlab.com/Winston-90/automatic_video_editing/).
The project has the following structure:

```
automatic_video_editing
├───article
├───models
│   ├───vosk-model-en-us-0.21
│   └───vosk-model-ru-0.10
├───videos
│   .gitignore
│   automatic_video_cutter.ipynb
│   Word.py
|
│   README.md
└── requirements.txt
```

Let’s talk about folders:
- The `article` folder contains the data for this tutorial.
- The `models` folder contains trained vosk models downloaded from [official site](https://alphacephei.com/vosk/models).
- The `videos` folder contains videos to be processed.
Сode files:
- `Word.py` file describes `Word` class.
- `automatic_video_cutter.ipynb` notebook contains full program with all the necessary verifications. You need to specify: path to the vosk model, path to video file, silence?
- 
- `script.py` file is ready-to-use python script. See `README.md` file for user manual. 

## Results and Conclusions

- Moviepy supports all video extensions supported by ffmpeg: .ogv, .mp4, .mpeg, .avi, .mov, .mkv etc.
- Quality of rendering
- Videos
- Times

https://zulko.github.io/moviepy/ref/VideoClip/VideoClip.html#moviepy.video.VideoClip.VideoClip.write_videofile

