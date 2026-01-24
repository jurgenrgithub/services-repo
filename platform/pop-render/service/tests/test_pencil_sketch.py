"""
Tests for Pencil Sketch rendering pipeline.

Verifies deterministic output and golden image comparison.
"""

import unittest
import os
import hashlib
from PIL import Image
import tempfile
import shutil

from pipelines.pencil_sketch import PencilSketchPipeline


class TestPencilSketchPipeline(unittest.TestCase):
    """Test cases for PencilSketchPipeline."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.test_dir = os.path.dirname(os.path.abspath(__file__))
        cls.fixtures_dir = os.path.join(cls.test_dir, 'fixtures')
        cls.test_input_path = os.path.join(cls.fixtures_dir, 'test_input.jpg')

        # Load test image
        if not os.path.exists(cls.test_input_path):
            raise FileNotFoundError(f"Test input not found: {cls.test_input_path}")

        cls.test_image = Image.open(cls.test_input_path)

    def setUp(self):
        """Set up each test."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up after each test."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pipeline_initialization(self):
        """Test pipeline can be initialized with default config."""
        pipeline = PencilSketchPipeline()
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.config, {})

    def test_pipeline_with_custom_config(self):
        """Test pipeline accepts custom configuration."""
        config = {'sigma': 15, 'contrast_factor': 1.5}
        pipeline = PencilSketchPipeline(algorithm_config=config)
        self.assertEqual(pipeline.config['sigma'], 15)
        self.assertEqual(pipeline.config['contrast_factor'], 1.5)

    def test_invalid_config_parameter(self):
        """Test pipeline rejects invalid configuration parameters."""
        config = {'invalid_param': 123}
        with self.assertRaises(ValueError):
            PencilSketchPipeline(algorithm_config=config)

    def test_invalid_sigma_value(self):
        """Test pipeline rejects invalid sigma values."""
        # sigma too small
        with self.assertRaises(ValueError):
            PencilSketchPipeline(algorithm_config={'sigma': 0})

        # sigma negative
        with self.assertRaises(ValueError):
            PencilSketchPipeline(algorithm_config={'sigma': -5})

    def test_invalid_contrast_value(self):
        """Test pipeline rejects invalid contrast values."""
        with self.assertRaises(ValueError):
            PencilSketchPipeline(algorithm_config={'contrast_factor': -1})

    def test_deterministic_output(self):
        """Test pipeline produces identical output for same input."""
        pipeline = PencilSketchPipeline()

        # Run pipeline twice
        result1 = pipeline.render(self.test_image.copy())
        result2 = pipeline.render(self.test_image.copy())

        # Convert to bytes for comparison
        import io
        buf1 = io.BytesIO()
        buf2 = io.BytesIO()
        result1.save(buf1, format='PNG')
        result2.save(buf2, format='PNG')

        # Compare pixel-perfect
        self.assertEqual(buf1.getvalue(), buf2.getvalue(),
                        "Pipeline output is not deterministic")

    def test_deterministic_with_custom_config(self):
        """Test deterministic output with custom configuration."""
        config = {'sigma': 15, 'contrast_factor': 1.2}
        pipeline = PencilSketchPipeline(algorithm_config=config)

        result1 = pipeline.render(self.test_image.copy())
        result2 = pipeline.render(self.test_image.copy())

        # Compare as numpy arrays
        import numpy as np
        arr1 = np.array(result1)
        arr2 = np.array(result2)

        self.assertTrue(np.array_equal(arr1, arr2),
                       "Output not deterministic with custom config")

    def test_different_sigma_produce_different_output(self):
        """Test different sigma values produce different results."""
        pipeline1 = PencilSketchPipeline(algorithm_config={'sigma': 10})
        pipeline2 = PencilSketchPipeline(algorithm_config={'sigma': 30})

        result1 = pipeline1.render(self.test_image.copy())
        result2 = pipeline2.render(self.test_image.copy())

        # Results should be different
        import numpy as np
        arr1 = np.array(result1)
        arr2 = np.array(result2)

        self.assertFalse(np.array_equal(arr1, arr2),
                        "Different sigma should produce different output")

    def test_output_mode_is_grayscale_by_default(self):
        """Test output image is in grayscale mode by default."""
        pipeline = PencilSketchPipeline()
        result = pipeline.render(self.test_image.copy())

        self.assertEqual(result.mode, 'L')

    def test_output_mode_rgb_when_configured(self):
        """Test output can be RGB when configured."""
        pipeline = PencilSketchPipeline(algorithm_config={'output_mode': 'RGB'})
        result = pipeline.render(self.test_image.copy())

        self.assertEqual(result.mode, 'RGB')

    def test_output_dimensions_preserved(self):
        """Test output has same dimensions as input."""
        pipeline = PencilSketchPipeline()
        result = pipeline.render(self.test_image.copy())

        self.assertEqual(result.size, self.test_image.size)

    def test_rgba_input_handled(self):
        """Test pipeline handles RGBA input correctly."""
        # Create RGBA test image
        rgba_image = self.test_image.copy().convert('RGBA')

        pipeline = PencilSketchPipeline()
        result = pipeline.render(rgba_image)

        self.assertEqual(result.mode, 'L')
        self.assertEqual(result.size, rgba_image.size)

    def test_grayscale_input_handled(self):
        """Test pipeline handles grayscale input correctly."""
        gray_image = self.test_image.copy().convert('L')

        pipeline = PencilSketchPipeline()
        result = pipeline.render(gray_image)

        self.assertEqual(result.mode, 'L')
        self.assertEqual(result.size, gray_image.size)

    def test_golden_image_hash(self):
        """
        Test output matches expected golden hash.

        This ensures the algorithm hasn't changed unexpectedly.
        If this test fails after intentional changes, update the golden hash.
        """
        pipeline = PencilSketchPipeline()
        result = pipeline.render(self.test_image.copy())

        # Save to bytes and compute hash
        import io
        buf = io.BytesIO()
        result.save(buf, format='PNG')
        result_hash = hashlib.sha256(buf.getvalue()).hexdigest()

        # Store golden hash in fixtures if it doesn't exist
        golden_hash_path = os.path.join(self.fixtures_dir, 'pencil_sketch_golden.hash')

        if os.path.exists(golden_hash_path):
            with open(golden_hash_path, 'r') as f:
                golden_hash = f.read().strip()

            self.assertEqual(result_hash, golden_hash,
                           f"Output hash {result_hash} doesn't match golden hash {golden_hash}")
        else:
            # First run: save golden hash
            with open(golden_hash_path, 'w') as f:
                f.write(result_hash)
            self.skipTest(f"Created golden hash file: {result_hash}")

    def test_reproducible_across_runs(self):
        """Test multiple instantiations produce same output."""
        results = []

        for _ in range(3):
            pipeline = PencilSketchPipeline()
            result = pipeline.render(self.test_image.copy())
            results.append(result)

        # All results should be identical
        import numpy as np
        arr0 = np.array(results[0])

        for i, result in enumerate(results[1:], 1):
            arr = np.array(result)
            self.assertTrue(np.array_equal(arr0, arr),
                           f"Run {i+1} differs from run 1")

    def test_color_dodge_blend_no_division_by_zero(self):
        """Test color dodge blend handles edge cases."""
        # Create a white image (should not crash with division by zero)
        white_image = Image.new('RGB', (100, 100), color='white')

        pipeline = PencilSketchPipeline()
        result = pipeline.render(white_image)

        self.assertIsNotNone(result)
        self.assertEqual(result.size, white_image.size)

    def test_black_image_handled(self):
        """Test pipeline handles black image correctly."""
        black_image = Image.new('RGB', (100, 100), color='black')

        pipeline = PencilSketchPipeline()
        result = pipeline.render(black_image)

        self.assertIsNotNone(result)
        self.assertEqual(result.size, black_image.size)

    def test_get_default_config(self):
        """Test get_default_config returns expected values."""
        pipeline = PencilSketchPipeline()
        defaults = pipeline.get_default_config()

        self.assertEqual(defaults['sigma'], 21)
        self.assertEqual(defaults['contrast_factor'], 1.3)
        self.assertEqual(defaults['output_mode'], 'L')


if __name__ == '__main__':
    unittest.main()
