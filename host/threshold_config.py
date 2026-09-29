"""Validated threshold settings shared by CLI, GUI and qualification capture."""
import math
import struct

DEFAULT=dict(ton=1048576,toff=262144,kon=8,koff=32,max_burst_samples=1048576)
PROFILES={'legacy':dict(on_multiple=4.0,off_multiple=2.0,kon=8,koff=32),
          'robust':dict(on_multiple=3.0,off_multiple=1.75,kon=16,koff=8)}


def validate(settings):
    for key in DEFAULT:
        if type(settings.get(key)) is not int:raise ValueError(f'{key} must be an integer')
    if not 0<=settings['toff']<settings['ton']<2**36:
        raise ValueError('Require 0 <= toff < ton < 2**36')
    if any(not 1<=settings[k]<=65535 for k in ('kon','koff')):
        raise ValueError('Confirmation lengths must be 1..65535')
    if settings['max_burst_samples']!=1048576:
        raise ValueError('This host supports max_burst_samples=1048576')
    return settings


def resolve(args,data):
    mode=getattr(args,'detector','threshold');gap=getattr(args,'gap_min',32)
    explicit=getattr(args,'threshold_config',None)
    profile=getattr(args,'threshold_profile','legacy')
    policy=getattr(args,'threshold_policy',None) or ('quiet-prefix' if profile=='robust' else 'fixed')
    overrides={k:getattr(args,k,None) for k in ('ton','toff','kon','koff')}
    if profile not in PROFILES or policy not in ('fixed','quiet-prefix'):
        raise ValueError('Unknown threshold profile or policy')
    if mode=='digital-zero' and (profile!='legacy' or policy!='fixed' or any(v is not None for v in overrides.values())):
        raise ValueError('Threshold options do not apply to digital-zero')
    settings=dict(DEFAULT,mode=mode,gap_min=gap)
    metadata=dict(profile=profile,policy=policy,requested_parameters=overrides,algorithm='sliding-energy-16-v1')
    if explicit is not None:
        if any(v is not None for v in overrides.values()) or profile!='legacy' or policy!='fixed':
            raise ValueError('Explicit qualification configuration conflicts with threshold options')
        settings.update(explicit)
        if settings['mode']!=mode or settings['gap_min']!=gap:raise ValueError('Detector configuration mismatch')
        metadata.update(profile='explicit',policy='explicit',requested_parameters=dict(explicit))
    else:
        choice=PROFILES[profile]
        settings.update(kon=choice['kon'],koff=choice['koff'])
        if profile=='robust' and policy!='quiet-prefix':
            raise ValueError('robust profile requires a declared quiet-prefix interval')
        if policy=='quiet-prefix':
            if overrides['ton'] is not None or overrides['toff'] is not None:
                raise ValueError('Explicit ton/toff conflict with quiet-prefix estimation')
            count=getattr(args,'quiet_samples',1024)
            if type(count) is not int or not 16<=count<=len(data)//4:
                raise ValueError('quiet_samples must be 16..input sample count')
            power=sum(i*i+q*q for i,q in struct.iter_unpack('<hh',data[:count*4]))/count
            # Strict sum < toff must remain reachable even for an all-zero
            # background. Keep at least one code of positive hysteresis.
            settings['ton']=max(2,math.ceil(16*power*choice['on_multiple']))
            settings['toff']=max(1,min(settings['ton']-1,math.ceil(16*power*choice['off_multiple'])))
            metadata.update(quiet_interval=[0,count],quiet_interval_assumption='User-declared leading background; no automatic silence detection',
                            estimated_background_power=power,on_multiple=choice['on_multiple'],off_multiple=choice['off_multiple'])
        elif (overrides['ton'] is None)!=(overrides['toff'] is None):
            raise ValueError('Specify both ton and toff')
        settings.update({k:v for k,v in overrides.items() if v is not None})
    validate(settings)
    return settings,metadata
