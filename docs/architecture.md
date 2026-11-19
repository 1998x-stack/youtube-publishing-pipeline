# Architecture

Pipeline: Colab → Drive assets → Manifest validation → SQLite queue → Private upload → Processing check → Cover/captions → YouTube publishAt → Reconciliation.

Domain has zero Google SDK dependencies. The application layer orchestrates source and publisher ports, while adapters implement Drive and YouTube APIs. SQLite is the P0 authoritative task journal, while YouTube itself is authoritative for remote video visibility.

Invariant: an immutable job ID and content fingerprint, mandatory editorial review and rights confirmation, exact OAuth channel guard, no automatic retry of ambiguous upload results, UTC scheduling and readback reconciliation.
