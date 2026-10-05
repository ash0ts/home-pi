# Example module template

Copy this directory to a valid module ID, then update `module.json` and the Compose service together. `_template` is excluded from the catalog. The placeholder image is intentionally unresolved.

Record the real use, selected upstream release/digest and ARM64 verification, application authentication, writable state, expected retention/storage, health probe, backup/restore steps, and update rollback. Use current upstream documentation for the selected image. No generic template can establish these service-specific facts.

Use a dedicated network and loopback listener; share a network only for a declared dependency that needs it. Relative bind paths resolve from the repository root, preserving the Compose project directory. Classify every writable mount and prove restore in isolation before deployment. No shell hooks or privileged containers belong in metadata.
