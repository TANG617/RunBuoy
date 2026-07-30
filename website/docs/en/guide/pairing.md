# Pair an iPhone

One iPhone can be paired with multiple Mac or Linux machines.

## Pair with a QR code

1. Open RunBuoy on your iPhone.
2. Open Settings and choose “Pair New Machine.”
3. Run this command on your computer:

```bash
runbuoy device pair
```

4. Scan the code and confirm the machine identity.

The QR code contains a short-lived pairing challenge, not a long-lived machine credential. It expires after five minutes and can be exchanged only once.

## Pair without scanning

Choose “Pair with Code” on the pairing screen and enter the six-digit code
printed by `runbuoy device pair`. Confirm the machine identity before pairing.

If you need to close the terminal and continue later:

```bash
runbuoy device pair --no-wait
# after scanning
runbuoy device pair --resume
```

The pending exchange secret is stored in the system keyring or in a local credential file with mode `0600`. It is never printed to the terminal.

## Check the connection

```bash
runbuoy doctor
runbuoy device status --check-server
runbuoy capabilities --json
```

An unreachable server does not weaken the security boundary or give the phone control over the computer.
