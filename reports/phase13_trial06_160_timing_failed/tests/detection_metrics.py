"""Predeclared one-to-one interval matching and explicit merge/split accounting."""
import numpy as np

MATCH_RULE=dict(minimum_truth_overlap=0.5,boundary_tolerance_samples=32,
                tie_break='descending IoU, descending intersection, earlier truth, earlier detection')


def evaluate(truth, detected, samples, sample_rate_hz=100000000):
    truth=[tuple(x) for x in truth]; detected=[tuple(x) for x in detected]
    overlap=np.zeros((len(truth),len(detected)),dtype=np.int64)
    candidates=[]
    for i,(a,b) in enumerate(truth):
        for j,(c,d) in enumerate(detected):
            amount=max(0,min(b,d)-max(a,c));overlap[i,j]=amount
            if amount >= (b-a)*MATCH_RULE['minimum_truth_overlap']:
                candidates.append((-amount/(max(b,d)-min(a,c)),-amount,i,j))
    chosen=[];used_truth=set();used_detection=set()
    for _,_,i,j in sorted(candidates):
        if i not in used_truth and j not in used_detection:
            used_truth.add(i);used_detection.add(j)
            a,b=truth[i];c,d=detected[j]
            errors=[c-a,d-b,(d-c)-(b-a)]
            chosen.append(dict(truth=i,detection=j,start_error_samples=errors[0],end_error_samples=errors[1],
                length_error_samples=errors[2],start_error_us=errors[0]*1e6/sample_rate_hz,
                end_error_us=errors[1]*1e6/sample_rate_hz,length_error_us=errors[2]*1e6/sample_rate_hz,
                within_boundary_tolerance=max(abs(errors[0]),abs(errors[1]))<=MATCH_RULE['boundary_tolerance_samples']))
    merges=int(np.count_nonzero((overlap>0).sum(axis=0)>1))
    splits=int(np.count_nonzero((overlap>0).sum(axis=1)>1))
    false_alarms=int(np.count_nonzero((overlap>0).sum(axis=0)==0))
    normal=sum(m['within_boundary_tolerance'] and np.count_nonzero(overlap[m['truth'],:])==1
               and np.count_nonzero(overlap[:,m['detection']])==1 for m in chosen)
    background_samples=samples-sum(b-a for a,b in truth)
    return dict(rule=MATCH_RULE,known_bursts=len(truth),detected_intervals=len(detected),matched=len(chosen),
        normal_matches=int(normal),normal_detection_rate=float(normal/len(truth)) if truth else None,
        missed=len(truth)-len(chosen),false_alarms=false_alarms,merged_detections=merges,split_truths=splits,
        unmatched_overlapping_detections=len(detected)-len(chosen)-false_alarms,
        detection_rate=len(chosen)/len(truth) if truth else None,
        background_observation_us=background_samples*1e6/sample_rate_hz,
        false_alarms_per_second=false_alarms/(background_samples/sample_rate_hz) if background_samples else None,
        matches=chosen)
