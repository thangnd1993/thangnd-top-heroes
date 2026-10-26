"""Owned Monthly daily row, independently of its upper advertisement entry."""
from top_heroes_auto.vision.guild_mail import components, contains, intersects, portrait


def controls(frame, role, color):
    label = frame.box(role)
    return [b for b in components(portrait(frame.captured), color)
            if label and contains(b, label) and 1.5 < b.width/b.height < 5]


def daily_geometry(frame, core):
    if (frame.page != 'shop-monthly' or not frame.box('monthly-daily-heading')
            or not frame.box('monthly-owned-label')
            or core is not frame.anchors.get('monthly-daily-claim') or not core.matched):
        raise ValueError('Owned Monthly daily panel is not qualified.')
    buttons = controls(frame, 'monthly-daily-claim', 'green')
    if len(buttons) != 1:
        raise ValueError('Monthly daily claim is missing or ambiguous.')
    box = buttons[0]
    heading, owned, back = (frame.box(r) for r in ('monthly-daily-heading','monthly-owned-label','back'))
    if not back or not heading.y+heading.height < owned.y < box.y < box.y+box.height < back.y:
        raise ValueError('Monthly daily reward is outside the current owned panel.')
    paid = [b for b in components(portrait(frame.captured), 'orange')
            if b.y > heading.y and 1.5 < b.width/b.height < 5 and b.height < owned.height*5]
    if any(intersects(box, b) for b in paid):
        raise ValueError('Monthly daily claim intersects paid activation/renewal.')
    # The intended target comes from the current enabled control, never its old position.
    return dict(bbox=vars(box), tap=list(core.device_box.center), forbidden=vars(paid[0]) if paid else
                dict(x=0,y=0,width=portrait(frame.captured).shape[1],height=heading.y),
                forbidden_regions=[vars(b) for b in paid], inside_allowed=True,
                outside_forbidden=True, confidence=core.score)


def daily_availability(detector, frame):
    core = frame.anchors['monthly-daily-claim']
    if not detector.selected_tab(frame, 'monthly') or not frame.box('monthly-daily-heading'):
        return 'UNKNOWN', core, None
    received = frame.anchors['monthly-daily-received']
    if (received.matched and core.score < core.threshold and frame.box('back')
            and frame.box('monthly-daily-heading').y < received.device_box.y
            and received.device_box.y+received.device_box.height < frame.box('back').y):
        return 'NOT_AVAILABLE', received, None
    if received.score >= received.threshold:
        return 'UNKNOWN', core, None
    # Run22 #3: an un-owned card shows its validity label and a paid activation
    # button where the claim would be. Positive label + no claim/received/owned
    # anchor anywhere = nothing free to collect; never a tap target.
    unowned = frame.anchors.get('monthly-unowned-label')
    owned = frame.anchors['monthly-owned-label']
    back = frame.box('back')
    if (unowned is not None and unowned.matched and unowned.device_box and back
            and core.score < core.threshold and not owned.matched and owned.score < owned.threshold
            and frame.box('monthly-daily-heading').y < unowned.device_box.y < back.y
            and not controls(frame, 'monthly-unowned-label', 'green')):
        return 'NOT_AVAILABLE', unowned, None
    try:
        daily_geometry(frame, core)
    except ValueError:
        return 'UNKNOWN', core, None
    return 'AVAILABLE', core, None
