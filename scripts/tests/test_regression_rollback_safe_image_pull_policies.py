"""Regression entry point for pinned images, cached pulls, and release rollback."""

import unittest

from scripts.tests import test_companion_helm


def load_tests(loader, tests, pattern):
    """Reuse the render contracts and their synthetic release image fixtures."""
    return loader.loadTestsFromNames(
        [
            "CompanionRenderTests.test_all_chart_workloads_default_to_pinned_images_and_cached_pulls",
            "CompanionRenderTests.test_release_values_restore_previous_images",
        ],
        module=test_companion_helm,
    )


if __name__ == "__main__":
    unittest.main()
