import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.main import main


@patch("src.main.Path.exists")
@patch("src.main.Path.glob")
@patch("src.main.DocumentPipeline")
@patch("builtins.open", new_callable=mock_open)
def test_main_successful_execution(
    mock_file_open: MagicMock,
    mock_pipeline_class: MagicMock,
    mock_glob: MagicMock,
    mock_exists: MagicMock,
) -> None:
    """Test successful execution of the main script with automatic processing approval."""
    # Simulate existing raw directory
    mock_exists.return_value = True
    
    # Simulate finding a supported file
    mock_file = MagicMock(spec=Path)
    mock_file.suffix = ".pdf"
    mock_file.stem = "dummy_doc"
    mock_glob.return_value = [mock_file]
    
    # Mock pipeline instance and its return value
    mock_pipeline_instance = mock_pipeline_class.return_value
    mock_result = MagicMock()
    mock_result.needs_review = False  # Approved branch
    mock_result.model_dump_json.return_value = '{"status": "success"}'
    mock_pipeline_instance.process.return_value = mock_result
    
    # Execute main; if it calls sys.exit(), the test will fail
    main()
    
    # Verify pipeline was called with the target file
    mock_pipeline_instance.process.assert_called_once_with(mock_file)
    mock_file_open.assert_called_once()


@patch("src.main.Path.exists")
def test_main_no_input_files(mock_exists: MagicMock) -> None:
    """Test script exits gracefully with code 1 when no files are found."""
    # Simulate empty directory
    mock_exists.return_value = False
    
    with pytest.raises(SystemExit) as exc_info:
        main()
        
    assert exc_info.value.code == 1


@patch("src.main.Path.exists")
@patch("src.main.Path.glob")
@patch("src.main.DocumentPipeline")
def test_main_pipeline_init_failure(
    mock_pipeline_class: MagicMock, 
    mock_glob: MagicMock, 
    mock_exists: MagicMock
) -> None:
    """Test script exits gracefully if the pipeline fails to initialize."""
    mock_exists.return_value = True
    
    mock_file = MagicMock(spec=Path)
    mock_file.suffix = ".pdf"
    mock_glob.return_value = [mock_file]
    
    # Simulate an error during Master Data loading
    mock_pipeline_class.side_effect = Exception("Master data missing")
    
    with pytest.raises(SystemExit) as exc_info:
        main()
        
    assert exc_info.value.code == 1


@patch("src.main.Path.exists")
@patch("src.main.Path.glob")
@patch("src.main.DocumentPipeline")
def test_main_processing_failure(
    mock_pipeline_class: MagicMock, 
    mock_glob: MagicMock, 
    mock_exists: MagicMock
) -> None:
    """Test script exits gracefully if document processing crashes."""
    mock_exists.return_value = True
    
    mock_file = MagicMock(spec=Path)
    mock_file.suffix = ".pdf"
    mock_glob.return_value = [mock_file]
    
    mock_pipeline_instance = mock_pipeline_class.return_value
    # Simulate runtime crash during LLM extraction
    mock_pipeline_instance.process.side_effect = Exception("API Timeout")
    
    with pytest.raises(SystemExit) as exc_info:
        main()
        
    assert exc_info.value.code == 1