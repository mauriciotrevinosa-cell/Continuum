# Kaggle ComfyUI session recovery

Continuum treats a Kaggle GPU notebook as disposable compute. A stopped session
cannot preserve GPU RAM or running processes, so recovery is based on durable,
reproducible state instead.

Before a planned stop, or automatically when the free-GPU setup script receives
Ctrl+C, create `/kaggle/working/continuum-recovery.tar.gz`. The bundle contains:

- `session-state.json` with ComfyUI/IP-Adapter revisions, model names, sizes and
  SHA-256 hashes, the last tunnel endpoint, and restart guidance;
- the session log when available;
- generated files currently under `ComfyUI/output/`.

The bundle intentionally does **not** duplicate multi-gigabyte checkpoint,
IP-Adapter, or CLIP Vision files. Their exact hashes are recorded instead so a
new ephemeral session can safely redownload and verify them. This keeps the
recovery artifact small enough to download or preserve as notebook output.

The archive still lives on the ephemeral machine until the creator downloads it
or preserves the notebook output. Do not assume stopping the accelerator saves
`/kaggle/working` automatically.

Manual checkpoint:

```bash
python scripts/kaggle_session_checkpoint.py \
  --workdir /kaggle/working/continuum-comfy \
  --session-log /kaggle/working/continuum-comfy/session.log
```

After creating the bundle, download it from the notebook Output panel (or keep
it as part of a saved notebook version) before ending the accelerator session.
