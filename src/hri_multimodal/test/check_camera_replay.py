#!/usr/bin/env python3
"""Replay a recorded webcam video through actual MediaPipe and temporal filter.

The optional generated Wave moves one real Open Palm image horizontally.
This is model/adapter evidence, not a live three-gesture human trial.
"""
import argparse
import json
import math
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

from hri_multimodal.vision import GestureFilter


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',required=True)
    parser.add_argument('--model',default='.models/gesture_recognizer.task')
    parser.add_argument('--output',default='artifacts/hri_multimodal/camera_replay.json')
    args=parser.parse_args()
    recognizer=mp.tasks.vision.GestureRecognizer.create_from_options(
        mp.tasks.vision.GestureRecognizerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=args.model),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,num_hands=2,
            min_hand_detection_confidence=.6,min_hand_presence_confidence=.6,
            min_tracking_confidence=.6))
    timestamp=0
    counts={}
    raw_counts={}
    best_palm=[0.,None]
    temporal=GestureFilter()

    def infer(frame,now):
        nonlocal timestamp
        timestamp+=50
        image=mp.Image(image_format=mp.ImageFormat.SRGB,
                       data=np.ascontiguousarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)))
        result=recognizer.recognize_for_video(image,timestamp)
        if len(result.hand_landmarks)!=1 or not result.gestures or not result.gestures[0]:
            return temporal.observe(now,'None',0.,len(result.hand_landmarks))[0]
        category=result.gestures[0][0]
        label,score=category.category_name,float(category.score)
        raw_counts[label]=raw_counts.get(label,0)+1
        if label=='Open_Palm' and score>best_palm[0]:
            points=result.hand_landmarks[0]
            h,w=frame.shape[:2]
            x1=max(0,int(min(p.x for p in points)*w)-45)
            x2=min(w,int(max(p.x for p in points)*w)+45)
            y1=max(0,int(min(p.y for p in points)*h)-45)
            y2=min(h,int(max(p.y for p in points)*h)+45)
            best_palm[:]=[score,frame[y1:y2,x1:x2].copy()]
        points=result.hand_landmarks[0]
        center=sum(points[i].x for i in (0,5,9,13,17))/5
        width=math.hypot(points[5].x-points[17].x,points[5].y-points[17].y)
        return temporal.observe(now,label,score,1,center,width)[0]

    capture=cv2.VideoCapture(args.video)
    index=0
    try:
        while True:
            ok,frame=capture.read()
            if not ok: break
            # Existing lab recordings append a status panel below 480px.
            label=infer(frame[:480],index/20.)
            counts[label]=counts.get(label,0)+1
            index+=1
        wave_counts={}
        if best_palm[1] is not None:
            temporal=GestureFilter()
            crop=best_palm[1].copy()
            scale=min(260/crop.shape[0],260/crop.shape[1])
            crop=cv2.resize(crop,None,fx=scale,fy=scale)
            palm=np.zeros((480,640,3),dtype=np.uint8)
            y=(480-crop.shape[0])//2
            x=(640-crop.shape[1])//2
            palm[y:y+crop.shape[0],x:x+crop.shape[1]]=crop
            for i,shift in enumerate(np.concatenate([
                    np.linspace(-70,70,8),np.linspace(70,-70,10),
                    np.linspace(-70,70,10),np.linspace(70,-70,10)])):
                shifted=cv2.warpAffine(palm,np.float32([[1,0,shift],[0,1,0]]),
                                       (palm.shape[1],palm.shape[0]))
                label=infer(shifted,(index+i)/20.)
                wave_counts[label]=wave_counts.get(label,0)+1
        result=dict(source=str(Path(args.video).resolve()),frames=index,
                    raw_counts=raw_counts,replay_counts=counts,translated_palm_counts=wave_counts,
                    limitation='Recorded webcam inference; Wave uses translated real palm image, not live human waving.',
                    passed=counts.get('Thumb Up',0)>0 and counts.get('Open Palm',0)>0
                    and wave_counts.get('Wave',0)>0)
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
        assert result['passed']
    finally:
        capture.release()
        recognizer.close()


if __name__=='__main__':
    main()
