"""
Tests for Pop Poster rendering pipeline.

Verifies deterministic output and golden image comparison.
"""

import unittest
import os
import hashlib
from PIL import Image
import tempfile
import shutil

from pipelines.pop_poster import PopPosterPipeline


class TestPopPosterPipeline(unittest.TestCase):
    """Test cases for PopPosterPipeline."""

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
        pipeline = PopPosterPipeline()
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.config, {})

    def test_pipeline_with_custom_config(self):
        """Test pipeline accepts custom configuration."""
        config = {'k': 6, 'seed': 99}
        pipeline = PopPosterPipeline(algorithm_config=config)
        self.assertEqual(pipeline.config['k'], 6)
        self.assertEqual(pipeline.config['seed'], 99)

    def test_invalid_config_parameter(self):
        """Test pipeline rejects invalid configuration parameters."""
        config = {'invalid_param': 123}
        with self.assertRaises(ValueError):
            PopPosterPipeline(algorithm_config=config)

    def test_invalid_k_value(self):
        """Test pipeline rejects invalid k values."""
        # k too small
        with self.assertRaises(ValueError):
            PopPosterPipeline(algorithm_config={'k': 1})

        # k too large
        with self.assertRaises(ValueError):
            PopPosterPipeline(algorithm_config={'k': 300})

        # k not an integer
        with self.assertRaises(ValueError):
            PopPosterPipeline(algorithm_config={'k': 5.5})

    def test_deterministic_output(self):
        """Test pipeline produces identical output for same input."""
        pipeline = PopPosterPipeline()

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
        config = {'k': 6, 'seed': 42, 'canny_low': 40, 'canny_high': 120}
        pipeline = PopPosterPipeline(algorithm_config=config)

        result1 = pipeline.render(self.test_image.copy())
        result2 = pipeline.render(self.test_image.copy())

        # Compare as numpy arrays
        import numpy as np
        arr1 = np.array(result1)
        arr2 = np.array(result2)

        self.assertTrue(np.array_equal(arr1, arr2),
                       "Output not deterministic with custom config")

    def test_different_seeds_produce_different_output(self):
        """Test different random seeds produce different results."""
        pipeline1 = PopPosterPipeline(algorithm_config={'seed': 42})
        pipeline2 = PopPosterPipeline(algorithm_config={'seed': 99})

        result1 = pipeline1.render(self.test_image.copy())
        result2 = pipeline2.render(self.test_image.copy())

        # Results should be different
        import numpy as np
        arr1 = np.array(result1)
        arr2 = np.array(result2)

        self.assertFalse(np.array_equal(arr1, arr2),
                        "Different seeds should produce different output")

    def test_output_mode_is_rgb(self):
        """Test output image is in RGB mode."""
        pipeline = PopPosterPipeline()
        result = pipeline.render(self.test_image.copy())

        self.assertEqual(result.mode, 'RGB')

    def test_output_dimensions_preserved(self):
        """Test output has same dimensions as input."""
        pipeline = PopPosterPipeline()
        result = pipeline.render(self.test_image.copy())

        self.assertEqual(result.size, self.test_image.size)

    def test_rgba_input_handled(self):
        """Test pipeline handles RGBA input correctly."""
        # Create RGBA test image
        rgba_image = self.test_image.copy().convert('RGBA')

        pipeline = PopPosterPipeline()
        result = pipeline.render(rgba_image)

        self.assertEqual(result.mode, 'RGB')
        self.assertEqual(result.size, rgba_image.size)

    def test_grayscale_input_handled(self):
        """Test pipeline handles grayscale input correctly."""
        gray_image = self.test_image.copy().convert('L')

        pipeline = PopPosterPipeline()
        result = pipeline.render(gray_image)

        self.assertEqual(result.mode, 'RGB')
        self.assertEqual(result.size, gray_image.size)

    def test_golden_image_hash(self):
        """
        Test output matches expected golden hash.

        This ensures the algorithm hasn't changed unexpectedly.
        If this test fails after intentional changes, update the golden hash.
        """
        pipeline = PopPosterPipeline()
        result = pipeline.render(self.test_image.copy())

        # Save to bytes and compute hash
        import io
        buf = io.BytesIO()
        result.save(buf, format='PNG')
        result_hash = hashlib.sha256(buf.getvalue()).hexdigest()

        # Store golden hash in fixtures if it doesn't exist
        golden_hash_path = os.path.join(self.fixtures_dir, 'pop_poster_golden.hash')

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
            pipeline = PopPosterPipeline()
            result = pipeline.render(self.test_image.copy())
            results.append(result)

        # All results should be identical
        import numpy as np
        arr0 = np.array(results[0])

        for i, result in enumerate(results[1:], 1):
            arr = np.array(result)
            self.assertTrue(np.array_equal(arr0, arr),
                           f"Run {i+1} differs from run 1")

    def test_get_default_config(self):
        """Test get_default_config returns expected values."""
        pipeline = PopPosterPipeline()
        defaults = pipeline.get_default_config()

        self.assertEqual(defaults['k'], 8)
        self.assertEqual(defaults['seed'], 42)
        self.assertIn('canny_low', defaults)
        self.assertIn('canny_high', defaults)
        self.assertIn('sharpen_radius', defaults)


if __name__ == '__main__':
    unittest.main()
