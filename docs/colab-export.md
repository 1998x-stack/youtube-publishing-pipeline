# Colab → Google Drive producer hand-off

Render the video on Colab first. The resulting local folder must contain a
valid manifest.json, video.mp4, and any optional thumbnail.png/subtitles.srt.

In your Colab notebook mount Drive:

    from google.colab import drive
    drive.mount('/content/drive')

Then run the exporter after installing this package:

    python -m youtube_pipeline.producer.colab_export \
      --source-dir /content/output/video-001 \
      --output-root /content/drive/MyDrive/youtube-pipeline/incoming

The exporter validates the manifest, requires rights and editorial approval,
copies the video in chunks, refuses overwriting existing jobs, and writes the
manifest **last**. Drive-mounted writes are not a distributed transaction:
the publisher still validates all required files when it materializes them.
Use a fresh job ID for each approved revision.

This exporter does not render media, generate voice or make rights decisions.
Use Colab GPUs for generation; run the publisher separately on a persistent
host. See README.zh.md for the follow-on scan/upload/reconcile commands.
