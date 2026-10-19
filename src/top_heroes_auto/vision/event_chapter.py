"""Known contribution chapter: current Back only; material action is unqualified."""
from top_heroes_auto.vision.dynamic_events import body_label_box


def chapter_navigation(image, back):
    h, w = image.shape[:2]
    if back is None or back.x > w*.18 or back.y < h*.9:
        return None
    personal = body_label_box(image, 'chapter-personal-contribution')
    guild = body_label_box(image, 'chapter-guild-contribution')
    materials = body_label_box(image, 'chapter-material-label')
    contribution = body_label_box(image, 'chapter-contribute-label')
    if not all((personal,guild,materials,contribution)):
        return None
    if not (personal.x+personal.width < guild.x and abs(personal.y-guild.y)<8
            and materials.x+materials.width < contribution.x
            and abs(materials.y-contribution.y)<8
            and personal.y+personal.height < materials.y < back.y
            and personal.center[0]<w*.5<guild.center[0]
            and materials.center[0]<w*.5<contribution.center[0]):
        return None
    return dict(page='event:contribution-chapter', title='contribution-chapter', back=back,
                tabs=[], selected=[], permission='KNOWN_BLOCKER_EXIT',
                blocking_reason='CHAPTER_MATERIAL_ACTION_AND_CONTRIBUTION_UNQUALIFIED',
                evidence=('paired-personal-guild-contribution-chests',
                          'paired-material-contribution-labels','current-back-only'))
