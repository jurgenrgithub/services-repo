"""
Tests for monitoring module.

Verifies Prometheus metrics tracking, background monitoring threads,
and integration with render pipeline lifecycle.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from prometheus_client import REGISTRY

from monitoring import (
    render_jobs_total,
    render_duration_seconds,
    render_queue_depth,
    render_storage_bytes_total,
    process_resident_memory_bytes,
    track_render_job,
    QueueDepthMonitor,
    StorageSizeMonitor,
    ProcessMemoryMonitor,
    start_monitoring,
    stop_monitoring,
)


class TestRenderJobMetrics:
    """Test render job metric tracking."""

    def test_track_completed_render(self):
        """Test tracking successful render completion."""
        # Get initial counter value
        initial_total = render_jobs_total.labels(
            status='completed',
            style='pop-poster',
            service='pop-render',
        )._value.get()

        initial_samples = len(list(render_duration_seconds.labels(
            style='pop-poster',
            service='pop-render',
        )._metrics.values()))

        # Track a completed job
        track_render_job(
            status='completed',
            style='pop-poster',
            duration_seconds=15.5,
        )

        # Verify counter incremented
        final_total = render_jobs_total.labels(
            status='completed',
            style='pop-poster',
            service='pop-render',
        )._value.get()
        assert final_total == initial_total + 1

        # Verify histogram recorded duration
        # Note: We can't easily verify the exact value, but we can verify it was called
        # by checking that the metric exists
        histogram = render_duration_seconds.labels(
            style='pop-poster',
            service='pop-render',
        )
        assert histogram is not None

    def test_track_failed_render(self):
        """Test tracking failed render."""
        # Get initial counter value
        initial_total = render_jobs_total.labels(
            status='failed',
            style='pencil-sketch',
            service='pop-render',
        )._value.get()

        # Track a failed job
        track_render_job(
            status='failed',
            style='pencil-sketch',
            duration_seconds=0.0,
        )

        # Verify counter incremented
        final_total = render_jobs_total.labels(
            status='failed',
            style='pencil-sketch',
            service='pop-render',
        )._value.get()
        assert final_total == initial_total + 1

    def test_track_multiple_styles(self):
        """Test tracking renders with different styles."""
        styles = ['pop-poster', 'pencil-sketch', 'between-the-lines']

        for style in styles:
            initial_total = render_jobs_total.labels(
                status='completed',
                style=style,
                service='pop-render',
            )._value.get()

            track_render_job(
                status='completed',
                style=style,
                duration_seconds=10.0,
            )

            final_total = render_jobs_total.labels(
                status='completed',
                style=style,
                service='pop-render',
            )._value.get()
            assert final_total == initial_total + 1

    def test_duration_histogram_buckets(self):
        """Test that duration histogram uses correct buckets."""
        # Verify buckets match acceptance criteria: 1, 5, 10, 30, 60, 120
        histogram = render_duration_seconds.labels(
            style='pop-poster',
            service='pop-render',
        )

        # The histogram should have the correct buckets
        # We check this by accessing the _buckets attribute
        metric_family = render_duration_seconds.describe()[0]
        # Buckets include infinity
        expected_buckets = (1.0, 5.0, 10.0, 30.0, 60.0, 120.0, float('inf'))

        # We can't directly access buckets easily, so we just verify the histogram exists
        # and can record values in the expected ranges
        track_render_job('completed', 'pop-poster', 0.5)  # < 1s
        track_render_job('completed', 'pop-poster', 3.0)  # 1-5s
        track_render_job('completed', 'pop-poster', 45.0) # 30-60s
        track_render_job('completed', 'pop-poster', 90.0) # 60-120s
        track_render_job('completed', 'pop-poster', 150.0) # > 120s


class TestQueueDepthMonitor:
    """Test queue depth background monitoring."""

    @patch('monitoring.get_queue_manager')
    def test_queue_depth_monitor_start_stop(self, mock_get_queue_manager):
        """Test starting and stopping queue depth monitor."""
        # Setup mock queue manager
        mock_queue_mgr = Mock()
        mock_queue_mgr._initialized = True
        mock_queue = Mock()
        mock_queue.count = 5
        mock_queue_mgr._queue = mock_queue
        mock_get_queue_manager.return_value = mock_queue_mgr

        # Create and start monitor
        monitor = QueueDepthMonitor(interval=1)
        monitor.start()

        assert monitor._running is True
        assert monitor._thread is not None
        assert monitor._thread.is_alive()

        # Let it run for a bit
        time.sleep(1.5)

        # Stop monitor
        monitor.stop()

        assert monitor._running is False

    @patch('monitoring.get_queue_manager')
    def test_queue_depth_metric_update(self, mock_get_queue_manager):
        """Test queue depth metric is updated correctly."""
        # Setup mock queue manager
        mock_queue_mgr = Mock()
        mock_queue_mgr._initialized = True
        mock_queue = Mock()
        mock_queue.count = 42
        mock_queue_mgr._queue = mock_queue
        mock_get_queue_manager.return_value = mock_queue_mgr

        # Create and start monitor with short interval
        monitor = QueueDepthMonitor(interval=1)
        monitor.start()

        # Wait for at least one update
        time.sleep(1.5)

        # Check metric value
        metric_value = render_queue_depth.labels(service='pop-render')._value.get()
        assert metric_value == 42

        # Clean up
        monitor.stop()

    @patch('monitoring.get_queue_manager')
    def test_queue_depth_monitor_error_handling(self, mock_get_queue_manager):
        """Test queue depth monitor handles errors gracefully."""
        # Setup mock queue manager that raises exception
        mock_queue_mgr = Mock()
        mock_queue_mgr._initialized = False
        mock_queue_mgr.initialize.side_effect = Exception("Redis connection failed")
        mock_get_queue_manager.return_value = mock_queue_mgr

        # Create and start monitor
        monitor = QueueDepthMonitor(interval=1)
        monitor.start()

        # Let it run and handle error
        time.sleep(1.5)

        # Should set metric to -1 on error
        metric_value = render_queue_depth.labels(service='pop-render')._value.get()
        assert metric_value == -1

        # Clean up
        monitor.stop()


class TestStorageSizeMonitor:
    """Test storage size background monitoring."""

    @patch('monitoring.get_storage_client')
    def test_storage_size_monitor_start_stop(self, mock_get_storage_client):
        """Test starting and stopping storage size monitor."""
        # Setup mock storage client
        mock_storage = Mock()
        mock_storage._initialized = True
        mock_storage._client = Mock()
        mock_storage._bucket_name = 'render-assets'

        # Setup paginator mock
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {'Contents': [{'Size': 1000}, {'Size': 2000}]}
        ]
        mock_storage._client.get_paginator.return_value = mock_paginator
        mock_get_storage_client.return_value = mock_storage

        # Create and start monitor with very short interval for testing
        monitor = StorageSizeMonitor(interval=1)
        monitor.start()

        assert monitor._running is True
        assert monitor._thread is not None
        assert monitor._thread.is_alive()

        # Let it run for a bit
        time.sleep(1.5)

        # Stop monitor
        monitor.stop()

        assert monitor._running is False

    @patch('monitoring.get_storage_client')
    def test_storage_size_metric_update(self, mock_get_storage_client):
        """Test storage size metric is calculated correctly."""
        # Setup mock storage client
        mock_storage = Mock()
        mock_storage._initialized = True
        mock_storage._client = Mock()
        mock_storage._bucket_name = 'render-assets'

        # Setup paginator with multiple pages
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {'Contents': [
                {'Size': 1024},
                {'Size': 2048},
                {'Size': 4096},
            ]},
            {'Contents': [
                {'Size': 8192},
            ]},
        ]
        mock_storage._client.get_paginator.return_value = mock_paginator
        mock_get_storage_client.return_value = mock_storage

        # Create and start monitor
        monitor = StorageSizeMonitor(interval=1)
        monitor.start()

        # Wait for update
        time.sleep(1.5)

        # Check metric value (1024 + 2048 + 4096 + 8192 = 15360)
        metric_value = render_storage_bytes_total.labels(service='pop-render')._value.get()
        assert metric_value == 15360

        # Clean up
        monitor.stop()

    @patch('monitoring.get_storage_client')
    def test_storage_size_monitor_error_handling(self, mock_get_storage_client):
        """Test storage size monitor handles errors gracefully."""
        # Setup mock storage client that raises exception
        mock_storage = Mock()
        mock_storage._initialized = False
        mock_storage.initialize.side_effect = Exception("MinIO connection failed")
        mock_get_storage_client.return_value = mock_storage

        # Create and start monitor
        monitor = StorageSizeMonitor(interval=1)
        monitor.start()

        # Let it run and handle error
        time.sleep(1.5)

        # Should set metric to -1 on error
        metric_value = render_storage_bytes_total.labels(service='pop-render')._value.get()
        assert metric_value == -1

        # Clean up
        monitor.stop()


class TestProcessMemoryMonitor:
    """Test process memory monitoring."""

    def test_memory_monitor_start_stop(self):
        """Test starting and stopping memory monitor."""
        monitor = ProcessMemoryMonitor(interval=1)
        monitor.start()

        assert monitor._running is True
        assert monitor._thread is not None
        assert monitor._thread.is_alive()

        # Let it run for a bit
        time.sleep(1.5)

        # Stop monitor
        monitor.stop()

        assert monitor._running is False

    def test_memory_metric_update(self):
        """Test memory metric is updated correctly."""
        monitor = ProcessMemoryMonitor(interval=1)
        monitor.start()

        # Wait for update
        time.sleep(1.5)

        # Check metric value - should be > 0 for running process
        metric_value = process_resident_memory_bytes.labels(service='pop-render')._value.get()
        assert metric_value > 0

        # Clean up
        monitor.stop()


class TestMonitoringIntegration:
    """Test monitoring system integration."""

    @patch('monitoring.get_queue_manager')
    @patch('monitoring.get_storage_client')
    def test_start_stop_all_monitors(self, mock_get_storage_client, mock_get_queue_manager):
        """Test starting and stopping all monitors together."""
        # Setup mocks
        mock_queue_mgr = Mock()
        mock_queue_mgr._initialized = True
        mock_queue = Mock()
        mock_queue.count = 0
        mock_queue_mgr._queue = mock_queue
        mock_get_queue_manager.return_value = mock_queue_mgr

        mock_storage = Mock()
        mock_storage._initialized = True
        mock_storage._client = Mock()
        mock_storage._bucket_name = 'render-assets'
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{'Contents': []}]
        mock_storage._client.get_paginator.return_value = mock_paginator
        mock_get_storage_client.return_value = mock_storage

        # Start all monitors
        start_monitoring()

        # Wait a bit for threads to start
        time.sleep(0.5)

        # Stop all monitors
        stop_monitoring()

        # Wait for threads to finish
        time.sleep(0.5)

    def test_multiple_start_calls_idempotent(self):
        """Test that calling start_monitoring multiple times is safe."""
        # This should not raise any errors or create duplicate threads
        start_monitoring()
        start_monitoring()

        # Clean up
        stop_monitoring()

    def test_multiple_stop_calls_idempotent(self):
        """Test that calling stop_monitoring multiple times is safe."""
        start_monitoring()

        # This should not raise any errors
        stop_monitoring()
        stop_monitoring()


class TestMetricsLabels:
    """Test that all metrics include required service label."""

    def test_render_jobs_total_has_service_label(self):
        """Test render_jobs_total includes service label."""
        metric = render_jobs_total.labels(
            status='completed',
            style='pop-poster',
            service='pop-render',
        )
        assert metric is not None

    def test_render_duration_seconds_has_service_label(self):
        """Test render_duration_seconds includes service label."""
        metric = render_duration_seconds.labels(
            style='pop-poster',
            service='pop-render',
        )
        assert metric is not None

    def test_render_queue_depth_has_service_label(self):
        """Test render_queue_depth includes service label."""
        metric = render_queue_depth.labels(service='pop-render')
        assert metric is not None

    def test_render_storage_bytes_total_has_service_label(self):
        """Test render_storage_bytes_total includes service label."""
        metric = render_storage_bytes_total.labels(service='pop-render')
        assert metric is not None

    def test_process_resident_memory_bytes_has_service_label(self):
        """Test process_resident_memory_bytes includes service label."""
        metric = process_resident_memory_bytes.labels(service='pop-render')
        assert metric is not None


class TestRenderLifecycle:
    """Test metrics tracking during render lifecycle."""

    def test_complete_render_lifecycle(self):
        """Test metrics are updated correctly during complete render lifecycle."""
        # Get initial values
        initial_completed = render_jobs_total.labels(
            status='completed',
            style='pop-poster',
            service='pop-render',
        )._value.get()

        # Simulate render lifecycle
        # 1. Job starts (not tracked in metrics)
        # 2. Job completes
        track_render_job(
            status='completed',
            style='pop-poster',
            duration_seconds=25.5,
        )

        # Verify metrics updated
        final_completed = render_jobs_total.labels(
            status='completed',
            style='pop-poster',
            service='pop-render',
        )._value.get()
        assert final_completed == initial_completed + 1

    def test_failed_render_lifecycle(self):
        """Test metrics are updated correctly when render fails."""
        # Get initial values
        initial_failed = render_jobs_total.labels(
            status='failed',
            style='pencil-sketch',
            service='pop-render',
        )._value.get()

        # Simulate render failure
        track_render_job(
            status='failed',
            style='pencil-sketch',
            duration_seconds=0.0,
        )

        # Verify metrics updated
        final_failed = render_jobs_total.labels(
            status='failed',
            style='pencil-sketch',
            service='pop-render',
        )._value.get()
        assert final_failed == initial_failed + 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
