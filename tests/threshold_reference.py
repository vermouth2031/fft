"""Interval/run-length threshold oracle, independent of the pipelined RTL FSM."""
import math
import numpy as np


def validate_detector(d):
    if d['mode'] not in ('threshold','digital-zero'):
        raise ValueError('Unknown detector mode')
    for key in ('ton','toff','kon','koff','gap_min','max_burst_samples'):
        if type(d[key]) is not int:
            raise ValueError('Detector parameters must be integers')
    if not 0 <= d['toff'] < d['ton'] < 2**36:
        raise ValueError('Require 0 <= toff < ton < 2**36')
    if any(not 1 <= d[k] <= 65535 for k in ('kon','koff','gap_min')):
        raise ValueError('Confirmation lengths must be 1..65535')
    if d['max_burst_samples'] != 1048576:
        raise ValueError('Qualification supports the baseline maximum burst length only')


def runs(mask):
    transitions=np.diff(np.r_[False,mask,False].astype(np.int8))
    return list(zip(np.flatnonzero(transitions==1).tolist(),np.flatnonzero(transitions==-1).tolist()))


def reference_threshold(iq, detector, finish=True):
    validate_detector(detector)
    p=np.asarray(iq,dtype=np.int64)
    power=p[:,0]**2+p[:,1]**2
    if len(power)>detector['max_burst_samples']:
        raise ValueError('Use per-period quiet-seam verification for long replay')
    prefix=np.r_[np.int64(0),np.cumsum(power)]
    sliding=prefix[1:]-prefix[np.maximum(0,np.arange(len(power))-15)]
    on=runs(sliding>detector['ton']);off=runs(sliding<detector['toff'])
    cursor=0; result=[]
    def next_run(intervals, after, confirmation):
        return next(((max(a,after),b) for a,b in intervals if b-max(a,after)>=confirmation),None)
    while candidate:=next_run(on,cursor,detector['kon']):
        start=candidate[0]
        ending=next_run(off,start+detector['kon'],detector['koff'])
        if ending is None and not finish:
            break
        end=ending[0] if ending else len(power)
        energy=int(prefix[end]-prefix[start]); peak=int(power[start:end].max())
        result.append(dict(start_sample=start,end_sample=end,length_samples=end-start,energy=energy,
            peak_q16=math.isqrt(peak<<32),rms_q16=math.isqrt((energy<<32)//(end-start)),flags=0 if ending else 256))
        if not ending:
            break
        cursor=end+detector['koff']
    return result
