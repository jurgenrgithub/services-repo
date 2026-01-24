"""
Tests for Between Lines rendering pipeline.

Verifies deterministic output and golden image comparison.
"""

import unittest
import os
import hashlib
from PIL import Image
import tempfile
import shutil

from pipelines.between_lines import BetweenLinesPipeline


class TestBetweenLinesPipeline(unittest.TestCase):
    """Test cases for BetweenLinesPipeline."""

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
        pipeline = BetweenLinesPipeline()
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.config, {})

    def test_pipeline_with_custom_config(self):
        """Test pipeline accepts custom configuration."""
        config = {'blur_length': 20, 'num_levels': 6}
        pipeline = BetweenLinesPipeline(algorithm_config=config)
        self.assertEqual(pipeline.config['blur_length'], 20)
        self.assertEqual(pipeline.config['num_levels'], 6)

    def test_invalid_config_parameter(self):
        """Test pipeline rejects invalid configuration parameters."""
        config = {'invalid_param': 123}
        with self.assertRaises(ValueError):
            BetweenLinesPipeline(algorithm_config=config)

    def test_invalid_blur_length_value(self):
        """Test pipeline rejects invalid blur_length values."""
        # blur_length too small
        with self.assertRaises(ValueError):
            BetweenLinesPipeline(algorithm_config={'blur_length': 0})

        # blur_length negative
        with self.assertRaises(ValueError):
            BetweenLinesPipeline(algorithm_config={'blur_length': -5})

    def test_invalid_num_levels_value(self):
        """Test pipeline rejects invalid num_levels values."""
        # num_levels too small
        with self.assertRaises(ValueError):
            BetweenLinesPipeline(algorithm_config={'num_levels': 1})

        # num_levels too large
        with self.assertRaises(ValueError):
            BetweenLinesPipeline(algorithm_config={'num_levels': 300})

    def test_deterministic_output(self):
        """Test pipeline produces identical output for same input."""
        pipeline = BetweenLinesPipeline()

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
        config = {'blur_length': 10, 'num_levels': 6, 'edge_threshold': 40}
        pipeline = BetweenLinesPipeline(algorithm_config=config)

        result1 = pipeline.render(self.test_image.copy())
        result2 = pipeline.render(self.test_image.copy())

        # Compare as numpy arrays
        import numpy as np
        arr1 = np.array(result1)
        arr2 = np.array(result2)

        self.assertTrue(np.array_equal(arr1, arr2),
                       "Output not deterministic with custom config")

    def test_different_blur_length_produce_different_output(self):
        """Test different blur_length values produce different results."""
        pipeline1 = BetweenLinesPipeline(algorithm_config={'blur_length': 5})
        pipeline2 = BetweenLinesPipeline(algorithm_config={'blur_length': 25})

        result1 = pipeline1.render(self.test_image.copy())
        result2 = pipeline2.render(self.test_image.copy())

        # Results should be different
        import numpy as np
        arr1 = np.array(result1)
        arr2 = np.array(result2)

        self.assertFalse(np.array_equal(arr1, arr2),
                        "Different blur_length should produce different output")

    def test_different_num_levels_produce_different_output(self):
        """Test different num_levels values produce different results."""
        pipeline1 = BetweenLinesPipeline(algorithm_config={'num_levels': 2})
        pipeline2 = BetweenLinesPipeline(algorithm_config={'num_levels': 8})

        result1 = pipeline1.render(self.test_image.copy())
        result2 = pipeline2.render(self.test_image.copy())

        # Results should be different
        import numpy as np
        arr1 = np.array(result1)
        arr2 = np.array(result2)

        self.assertFalse(np.array_equal(arr1, arr2),
                        "Different num_levels should produce different output")

    def test_output_dimensions_preserved(self):
        """Test output has same dimensions as input."""
        pipeline = BetweenLinesPipeline()
        result = pipeline.render(self.test_image.copy())

        self.assertEqual(result.size, self.test_image.size)

    def test_rgba_input_handled(self):
        """Test pipeline handles RGBA input correctly."""
        # Create RGBA test image
        rgba_image = self.test_image.copy().convert('RGBA')

        pipeline = BetweenLinesPipeline()
        result = pipeline.render(rgba_image)

        # Should convert to RGB for color inputs
        self.assertIn(result.mode, ['L', 'RGB'])
        self.assertEqual(result.size, rgba_image.size)

    def test_grayscale_input_handled(self):
        """Test pipeline handles grayscale input correctly."""
        gray_image = self.test_image.copy().convert('L')

        pipeline = BetweenLinesPipeline()
        result = pipeline.render(gray_image)

        self.assertIn(result.mode, ['L', 'RGB'])
        self.assertEqual(result.size, gray_image.size)

    def test_golden_image_hash(self):
        """
        Test output matches expected golden hash.

        This ensures the algorithm hasn't changed unexpectedly.
        If this test fails after intentional changes, update the golden hash.
        """
        pipeline = BetweenLinesPipeline()
        result = pipeline.render(self.test_image.copy())

        # Save to bytes and compute hash
        import io
        buf = io.BytesIO()
        result.save(buf, format='PNG')
        result_hash = hashlib.sha256(buf.getvalue()).hexdigest()

        # Store golden hash in fixtures if it doesn't exist
        golden_hash_path = os.path.join(self.fixtures_dir, 'between_lines_golden.hash')

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
            pipeline = BetweenLinesPipeline()
            result = pipeline.render(self.test_image.copy())
            results.append(result)

        # All results should be identical
        import numpy as np
        arr0 = np.array(results[0])

        for i, result in enumerate(results[1:], 1):
            arr = np.array(result)
            self.assertTrue(np.array_equal(arr0, arr),
                           f"Run {i+1} differs from run 1")

    def test_posterization_levels(self):
        """Test posterization produces correct number of unique values."""
        pipeline = BetweenLinesPipeline(algorithm_config={'num_levels': 4})
        result = pipeline.render(self.test_image.copy())

        import numpy as np
        arr = np.array(result)

        # For grayscale output, count unique values
        if result.mode == 'L':
            unique_values = np.unique(arr)
            # Should have at most num_levels unique values (could be fewer if image is simple)
            self.assertLessEqual(len(unique_values), 4,
                               "Posterization should limit to num_levels values")

    def test_edge_detection_on_uniform_image(self):
        """Test pipeline handles uniform image (no edges)."""
        uniform_image = Image.new('RGB', (100, 100), color='gray')

        pipeline = BetweenLinesPipeline()
        result = pipeline.render(uniform_image)

        self.assertIsNotNone(result)
        self.assertEqual(result.size, uniform_image.size)

    def test_get_default_config(self):
        """Test get_default_config returns expected values."""
        pipeline = BetweenLinesPipeline()
        defaults = pipeline.get_default_config()

        self.assertEqual(defaults['blur_length'], 15)
        self.assertEqual(defaults['num_levels'], 4)
        self.assertIn('edge_threshold', defaults)


if __name__ == '__main__':
    unittest.main()
