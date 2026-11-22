# Frosty Attendance Bot

Discord bot for daily event attendance sign-ups (10 max per day, 4 max per week) with an automatic 7:00 AM PHT (`Asia/Manila`) post and weekly Monday reset.

## Environment Variables
- `TOKEN`: Discord bot token.
- `CHANNEL_ID`: Numeric Discord channel ID where the daily event post is sent.

## Admin Commands
- `!startevent`: Manually posts an attendance card.
- `!reset`: Resets weekly attendance counts to `0` for everyone.
- `!checklimits`: Shows users who have hit `4/4` sessions this week.
- `!test7am`: Runs a diagnostic check and triggers the 7:00 AM deployment logic immediately.
