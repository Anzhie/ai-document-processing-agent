import logging
import sys
from pathlib import Path

from src.pipeline import DocumentPipeline

# Configure logging for standard output tracking
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

    # Find the first supported input file in the raw data directory
    target_file = None
    if raw_dir.exists():
        for file_path in raw_dir.glob("*.*"):
            if file_path.suffix.lower() in supported_extensions:
                target_file = file_path
                break

    if not target_file:
        logger.error("No input document found in 'data/raw/' directory.")
        sys.exit(1)

    logger.info("Initializing pipeline with Master Data...")
    try:
        pipeline = DocumentPipeline()
    except Exception:
        logger.exception("Pipeline initialization failed")
        sys.exit(1)

    logger.info("Processing document: %s", target_file)
    try:
        # Execute the end-to-end document processing lifecycle
        result = pipeline.process(target_file)
        
        # Save the final JSON output to the output directory
        output_file = output_dir / f"{target_file.stem}_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        
        logger.info("Saved result to: %s", output_file)
        
        # Print the structured payload to the console for review
        print("\n" + "=" * 60)
        print("STRUCTURED OUTPUT (JSON):")
        print("=" * 60)
        print(result.model_dump_json(indent=2))
        print("=" * 60 + "\n")

        # Implement processing routing based on Case Study requirements[span_4](start_span)[span_4](end_span)
        if result.needs_review:
            logger.warning("ROUTING: MANUAL REVIEW REQUIRED ⚠️")
            for reason in result.review_reasons:
                logger.warning(" - %s", reason)
        else:
            logger.info("ROUTING: AUTOMATIC PROCESSING APPROVED ✅")
            logger.info("Document passed all confidence and business validations.")
            
    except Exception:
        logger.exception("Error processing document")
        sys.exit(1)


if __name__ == "__main__":
    main()