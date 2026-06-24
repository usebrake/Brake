# Brake User Guide

Brake is a Windows accountability app for explicit screen content.

It runs locally on your computer. It checks screenshots on your device, uses local detection models, and triggers lockouts when explicit content appears. It does not upload, save, or send screenshots.

## The short version

1. Install Brake.
2. Open Brake from the Start Menu.
3. Save the recovery code shown on first launch.
4. Choose your lockout length. The default is 15 minutes.
5. Turn on protection and set a password.
6. Optional: lock in a commitment so the password cannot turn protection off early.

## What protection means

When protection is on, Brake checks the screen in the background. It watches and reacts; it does not block websites or apps.

Clear explicit content triggers a full lockout. Sustained or repeated context nudity can also trigger a full lockout when it persists over time. Repeated full lockouts within 24 hours can make the next lockout longer.

Brake no longer uses the short incidental nudity warning lockout. Brief movie/TV nudity should usually pass, but repeatedly visible context nudity is treated as intentional viewing.

## Detection

Brake uses one default detection policy. Clear explicit content triggers the full lockout through the normal confirmation flow, and repeated context nudity can escalate when it persists. The app does not expose separate sensitivity mode choices.

## Commitment

Without a commitment, your normal password can turn protection off anytime. Commitment locks protection in for a set time so the password cannot turn protection off early.

You can make Brake stricter during commitment, but you cannot make it easier to bypass. For example, you cannot turn off shutdown after lockout or disable illustrated detection until the commitment ends.

## Recovery code

Your recovery code is shown once on first launch.

It can reset your password immediately. It can also start an emergency cooldown before Brake turns protection off, including during a commitment. The default cooldown is 15 minutes and can be changed in Advanced.

Do not keep the recovery code somewhere easy to reach on the same computer. Write it on paper, take a photo on your phone, or give it to someone you trust. If you want the strongest commitment, you can choose not to copy it, but a forgotten password may require a full reset.

Advanced also has a lockout recovery setting. When it is on, a small emergency option appears during a full lockout. Entering the recovery code there starts a separate lockout recovery cooldown, skips shutdown at the end, and leaves protection on.

## Illustrated content

Illustrated detection is optional. If drawings, anime, or rendered explicit content are a risk for you, turn it on in the Illustrated tab. It downloads a separate local model the first time you install it.

When illustrated detection is off, Brake ignores illustrated detections. When it is on, high-confidence illustrated explicit content can trigger a full lockout.

## What Brake does not promise

Brake adds friction. It is not magic.

A determined Windows administrator can eventually bypass local software. Safe Mode, another operating system, another device, or deleting source files are outside the current beta protection model.

The goal is to make the impulse harder to act on, not to claim perfect control over the computer.
