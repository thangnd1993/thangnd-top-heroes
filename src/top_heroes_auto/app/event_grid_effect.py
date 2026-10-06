"""Explicit claimed-card proof from saved current frames; never sends input."""
import cv2
import numpy as np

from top_heroes_auto.ldplayer.identity import runtime_key
from top_heroes_auto.vision.event_task_grid import grid_label_glyph, task_grid_rows, task_grid_shell
from top_heroes_auto.vision.local_ocr import read_words


def claimed_grid_effect(proof,captures,*,reader=read_words):
    from top_heroes_auto.app.event_task_effect import saved_frame

    if len(captures)!=2 or len(set(map(str,captures)))!=2 or not proof['page'].endswith(':race-task-grid'):
        return []
    before,meta,shot=saved_frame(proof['capture'])
    if (runtime_key(meta['frame']['identity'])!=runtime_key(proof['identity']) or meta['frame']['page']!=proof['page']
            or not meta.get('entered_event')):
        return []
    shell=task_grid_shell(before)
    if shell is None or proof['event']!=shell['title']:
        return []
    targets=[r for r in task_grid_rows(before,shell,reader=reader)
             if r['identity']==proof['reward'] and r['state']=='AVAILABLE']
    if len(targets)!=1 or list(targets[0]['box'].center)!=proof.get('tap'):
        return []
    controls=[c for c in meta['frame']['controls'] if c['kind']=='reward' and c['identity']==proof['reward']]
    if (len(controls)!=1 or controls[0]['cost']!='FREE' or not controls[0]['available']
            or controls[0]['box']!=vars(targets[0]['box'])):
        return []
    original=grid_label_glyph(before,targets[0]['row'])
    observations=[]
    for path in captures:
        after,metadata,screenshot=saved_frame(path)
        if (runtime_key(metadata['frame']['identity'])!=runtime_key(proof['identity'])
                or metadata['frame']['page']!=proof['page']
                or metadata.get('entered_event')!=meta['entered_event']
                or metadata['frame'].get('popup')
                or screenshot['timestamp']<=shot['timestamp']):
            return []
        shell=task_grid_shell(after)
        if shell is None:
            return []
        targets=[r for r in task_grid_rows(after,shell,reader=reader)
                 if r['identity']==proof['reward']]
        if (len(targets)!=1 or targets[0]['state']!='NOT_AVAILABLE'
                or not {'explicit-claimed-label','original-green-control-absent'}.issubset(targets[0]['evidence'])):
            return []
        glyph=grid_label_glyph(after,targets[0]['row'])
        if original is None or glyph is None:
            return []
        score=float(cv2.matchTemplate(glyph,original,cv2.TM_CCOEFF_NORMED)[0,0])
        if not np.isfinite(score) or score<.98:
            return []
        observations.append(dict(identity=list(proof['identity']),capture=str(path),event=proof['event'],
            page=proof['page'],reward=proof['reward'],state='NOT_AVAILABLE',
            independent_evidence=['same-qualified-task-grid','unique-saved-caption-agreement',
                                  'explicit-claimed-label','original-green-control-absent','complete-reward-card'],
            caption_confidence=score,receipt_required=False))
    return observations
