# Bridge Design

The legacy bridge batches transfers every fifteen minutes. A transfer becomes final after twelve network blocks.

## Security assumptions

Validators sign each batch. Users should verify the destination network before submitting a transfer.

## Long design notes

The bridge separates observation, validation, signing, submission, and settlement. Observation reads finalized source-chain events. Validation checks asset, amount, destination, nonce, and replay protection. Signing requires the configured validator quorum. Submission sends one bounded batch to the destination chain. Settlement records the destination transaction and exposes an auditable identifier. Operators monitor each stage independently so a delayed observer does not look like a failed settlement. The mechanism was designed for the original network configuration and remains useful historical context, but operational parameters may be revised by current product documentation.
