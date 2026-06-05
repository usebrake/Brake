# Brake User Guide

Brake is a Windows accountability app for explicit screen content.

It runs locally on your computer. It checks screenshots on your device, uses local detection models, and triggers lockouts when explicit content appears. It does not upload, save, or send screenshots.

## The short version

1. Install Brake.
2. Open Brake from the Start Menu.
3. Save the recovery code shown on first launch.
4. Choose your lockout length. The default is 10 minutes.
5. Turn on protection and set a password.
6. Optional: lock in a commitment so the password cannot turn protection off early.

## What protection means

When protection is on, Brake checks the screen in the background.

Clear explicit content triggers a full lockout. When that lockout ends, Windows shuts down. After restart, Brake watches strictly for five minutes so the same content cannot be reopened immediately.

Incidental or partial nudity is handled according to your sensitivity setting. Light ignores most of it. Balanced gives one warning first, then escalates repeated nudity. Strict treats confirmed nudity as a full lockout.

## Sensitivity

Light: lowest false-positive risk. Clear explicit content only.

Balanced: recommended. Clear explicit content locks. Nudity gets a short warning first. If nudity keeps appearing after the warning, Brake escalates to the full lockout.

Strict: strongest response. Clear explicit content locks immediately. Partial nudity gets a fast second scan; if it is confirmed, Brake triggers the full lockout.

## Commitment

Commitment locks protection in for a set time. During a commitment, your normal password cannot turn protection off.

You can make Brake stricter during commitment, but you cannot make it easier to bypass. For example, you can raise sensitivity, but you cannot lower it until the commitment ends.

## Recovery code

Your recovery code is shown once on first launch.

It can reset your password immediately. It can also start a 10-minute emergency cooldown before Brake turns protection off, including during a commitment.

Do not keep the recovery code somewhere easy to reach on the same computer. Write it on paper, take a photo on your phone, or give it to someone you trust. If you want the strongest commitment, you can choose not to copy it, but a forgotten password may require a full reset.

## Anime and illustrated content

Anime detection is optional. It downloads a separate local model the first time you install it.

Not strict: illustrated NSFW gets a short pause only.

Strict: very high-confidence illustrated explicit content can trigger a full lockout. Lower-confidence hits get a short pause.

## What Brake does not promise

Brake adds friction. It is not magic.

A determined Windows administrator can eventually bypass local software. Safe Mode, another operating system, another device, or deleting source files are outside the current beta protection model.

The goal is to make the impulse harder to act on, not to claim perfect control over the computer.
