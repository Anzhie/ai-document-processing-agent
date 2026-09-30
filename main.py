import logging
import sys
import time
from pathlib import Path

from src.pipeline import DocumentPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point to execute the pipeline on incoming documents."""
    raw_dir = Path("data/raw")
    output_dir = Path("data/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    supported_extensions = {".xlsx", ".xls", ".csv", ".pdf", ".png", ".jpg", ".jpeg", ".tiff"}

    if not raw_dir.exists():
        logger.error("Directory 'data/raw/' does not exist.")
        sys.exit(1)

    target_files = [
        f for f in raw_dir.glob("*.*") if f.suffix.lower() in supported_extensions
    ]

    if not target_files:
        logger.error("No supported input documents found in 'data/raw/' directory.")
        sys.exit(1)

    logger.info("Initializing pipeline with Master Data...")
    try:
        pipeline = DocumentPipeline()
    except Exception:
        logger.exception("Pipeline initialization failed")
        sys.exit(1)

    # Process all discovered documents with throttling
    for target_file in target_files:
        logger.info("Processing document: %s", target_file)
        try:
            result = pipeline.process(target_file)
            
            output_file = output_dir / f"{target_file.stem}_result.json"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result.model_dump_json(indent=2))
            
            logger.info("Saved result to: %s", output_file)
            
            if result.needs_review:
                logger.warning("ROUTING: MANUAL REVIEW REQUIRED ⚠️ [%s]", target_file.name)
                for reason in result.review_reasons:
                    logger.warning(" - %s", reason)
            else:
                logger.info("ROUTING: AUTOMATIC PROCESSING APPROVED ✅ [%s]", target_file.name)
                
        except Exception:
            logger.exception("Error processing document %s", target_file)

        # Pause briefly to respect Groq API rate limits (OTPM)
        time.sleep(3)


if __name__ == "__main__":
    main()