"""Tests for the deduplication module."""

import hashlib

import pytest

from iracing_setup_downloader.deduplication import (
    DuplicateDetector,
    DuplicateInfo,
    FileHashCache,
)


class TestFileHashCache:
    """Tests for FileHashCache class."""

    def test_compute_hash_from_bytes(self):
        """Test computing hash from bytes."""
        cache = FileHashCache()
        content = b"test content"
        expected = hashlib.sha256(content).hexdigest()

        result = cache.compute_hash_from_bytes(content)

        assert result == expected
        assert len(result) == 64  # SHA-256 hex length

    def test_get_hash_computes_file_hash(self, tmp_path):
        """Test get_hash computes correct SHA-256 hash."""
        cache = FileHashCache()
        test_file = tmp_path / "test.sto"
        content = b"setup file content"
        test_file.write_bytes(content)

        result = cache.get_hash(test_file)

        expected = hashlib.sha256(content).hexdigest()
        assert result == expected

    def test_get_hash_caches_result(self, tmp_path):
        """Test that get_hash uses cache on second call."""
        cache = FileHashCache()
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        # First call computes
        hash1 = cache.get_hash(test_file)
        # Second call should use cache
        hash2 = cache.get_hash(test_file)

        assert hash1 == hash2
        # Both should be in cache
        assert str(test_file.resolve()) in cache._cache

    def test_get_hash_invalidates_on_mtime_change(self, tmp_path):
        """Test cache invalidation when file modification time changes."""
        import os
        import time

        cache = FileHashCache()
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"original content")

        hash1 = cache.get_hash(test_file)

        # Ensure mtime changes by waiting and touching the file
        time.sleep(0.01)  # Small delay to ensure mtime changes
        test_file.write_bytes(b"modified content")
        # Force mtime update to ensure it's different
        os.utime(test_file, None)

        hash2 = cache.get_hash(test_file)

        assert hash1 != hash2

    def test_get_hash_file_not_found(self, tmp_path):
        """Test get_hash raises error for nonexistent file."""
        cache = FileHashCache()
        nonexistent = tmp_path / "nonexistent.sto"

        with pytest.raises(FileNotFoundError):
            cache.get_hash(nonexistent)

    def test_preload_directory_empty(self, tmp_path):
        """Test preloading an empty directory."""
        cache = FileHashCache()
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = cache.preload_directory(empty_dir, show_progress=False)

        assert result == {}

    def test_preload_directory_nonexistent(self, tmp_path):
        """Test preloading a nonexistent directory."""
        cache = FileHashCache()

        result = cache.preload_directory(tmp_path / "nonexistent", show_progress=False)

        assert result == {}

    def test_preload_directory_with_files(self, tmp_path):
        """Test preloading directory with multiple files."""
        cache = FileHashCache()
        content1 = b"content one"
        content2 = b"content two"

        (tmp_path / "file1.sto").write_bytes(content1)
        (tmp_path / "file2.sto").write_bytes(content2)

        result = cache.preload_directory(tmp_path, show_progress=False)

        assert len(result) == 2
        hash1 = hashlib.sha256(content1).hexdigest()
        hash2 = hashlib.sha256(content2).hexdigest()
        assert hash1 in result
        assert hash2 in result

    def test_preload_directory_detects_duplicates(self, tmp_path):
        """Test preloading detects duplicate content files."""
        cache = FileHashCache()
        duplicate_content = b"duplicate content"

        (tmp_path / "file1.sto").write_bytes(duplicate_content)
        (tmp_path / "file2.sto").write_bytes(duplicate_content)
        (tmp_path / "file3.sto").write_bytes(b"unique content")

        result = cache.preload_directory(tmp_path, show_progress=False)

        # Should have 2 unique hashes
        assert len(result) == 2
        # Duplicate hash should have 2 paths
        dup_hash = hashlib.sha256(duplicate_content).hexdigest()
        assert len(result[dup_hash]) == 2

    def test_preload_directory_recursive(self, tmp_path):
        """Test preloading finds files in subdirectories."""
        cache = FileHashCache()
        subdir = tmp_path / "car" / "track"
        subdir.mkdir(parents=True)

        (tmp_path / "root.sto").write_bytes(b"root")
        (subdir / "nested.sto").write_bytes(b"nested")

        result = cache.preload_directory(tmp_path, show_progress=False)

        assert len(result) == 2

    def test_preload_directory_filters_pattern(self, tmp_path):
        """Test preloading only matches the specified pattern."""
        cache = FileHashCache()

        (tmp_path / "setup.sto").write_bytes(b"setup")
        (tmp_path / "readme.txt").write_bytes(b"readme")

        result = cache.preload_directory(tmp_path, pattern="*.sto", show_progress=False)

        assert len(result) == 1

    def test_invalidate_removes_from_cache(self, tmp_path):
        """Test invalidate removes file from cache."""
        cache = FileHashCache()
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        cache.get_hash(test_file)
        assert str(test_file.resolve()) in cache._cache

        cache.invalidate(test_file)

        assert str(test_file.resolve()) not in cache._cache

    def test_clear_empties_cache(self, tmp_path):
        """Test clear removes all entries."""
        cache = FileHashCache()
        (tmp_path / "file1.sto").write_bytes(b"one")
        (tmp_path / "file2.sto").write_bytes(b"two")

        cache.preload_directory(tmp_path, show_progress=False)
        assert len(cache._cache) == 2

        cache.clear()

        assert len(cache._cache) == 0


class TestFileHashCachePersistence:
    """Tests for FileHashCache persistence functionality."""

    def test_save_and_load(self, tmp_path):
        """Test saving and loading cache."""
        cache_file = tmp_path / "cache.json"
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"test content")

        # Create cache, hash a file, and save
        cache1 = FileHashCache(cache_file=cache_file)
        cache1.load()
        hash1 = cache1.get_hash(test_file)
        cache1.save()

        assert cache_file.exists()

        # Load in a new cache instance
        cache2 = FileHashCache(cache_file=cache_file)
        cache2.load()

        # Should have the entry
        assert str(test_file.resolve()) in cache2._cache
        cached_hash, _, _ = cache2._cache[str(test_file.resolve())]
        assert cached_hash == hash1

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading when cache file doesn't exist."""
        cache_file = tmp_path / "nonexistent.json"
        cache = FileHashCache(cache_file=cache_file)

        cache.load()

        assert cache.is_loaded
        assert len(cache._cache) == 0

    def test_load_skips_invalid_entries(self, tmp_path):
        """Test that invalid entries are skipped during load."""
        import json

        cache_file = tmp_path / "cache.json"
        data = {
            "version": 1,
            "/valid/path": {"hash": "abc123", "mtime_ns": 1000, "size": 100},
            "/invalid/missing_hash": {"mtime_ns": 1000, "size": 100},
            "/invalid/wrong_type": "not a dict",
            "/invalid/wrong_mtime": {"hash": "abc", "mtime_ns": "not_int", "size": 100},
        }
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        cache = FileHashCache(cache_file=cache_file)
        cache.load()

        # Only the valid entry should be loaded
        assert len(cache._cache) == 1
        assert "/valid/path" in cache._cache

    def test_load_handles_newer_version(self, tmp_path):
        """Test that newer cache versions result in empty cache."""
        import json

        cache_file = tmp_path / "cache.json"
        data = {
            "version": 999,
            "/some/path": {"hash": "abc123", "mtime_ns": 1000, "size": 100},
        }
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        cache = FileHashCache(cache_file=cache_file)
        cache.load()

        # Should start with empty cache due to version mismatch
        assert cache.is_loaded
        assert len(cache._cache) == 0

    def test_save_creates_parent_dirs(self, tmp_path):
        """Test that save creates parent directories."""
        cache_file = tmp_path / "nested" / "deep" / "cache.json"
        cache = FileHashCache(cache_file=cache_file)
        cache.load()

        # Hash a file to trigger modification
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")
        cache.get_hash(test_file)

        cache.save()

        assert cache_file.exists()
        assert cache_file.parent.exists()

    def test_save_skips_if_not_loaded(self, tmp_path):
        """Test that save does nothing if not loaded."""
        cache_file = tmp_path / "cache.json"
        cache = FileHashCache(cache_file=cache_file)

        cache.save()  # Should not raise

        assert not cache_file.exists()

    def test_save_skips_if_not_modified(self, tmp_path):
        """Test that save skips if cache wasn't modified."""
        import json

        cache_file = tmp_path / "cache.json"
        original_data = {
            "version": 1,
            "/some/path": {"hash": "abc123", "mtime_ns": 1000, "size": 100},
        }
        cache_file.write_text(json.dumps(original_data), encoding="utf-8")

        cache = FileHashCache(cache_file=cache_file)
        cache.load()

        # Don't modify, just save
        original_mtime = cache_file.stat().st_mtime_ns

        import time

        time.sleep(0.01)  # Ensure time passes
        cache.save()

        # File should not have been rewritten
        assert cache_file.stat().st_mtime_ns == original_mtime

    def test_cleanup_stale_removes_missing_files(self, tmp_path):
        """Test cleanup_stale removes entries for missing files."""
        cache_file = tmp_path / "cache.json"
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        cache = FileHashCache(cache_file=cache_file)
        cache.load()
        cache.get_hash(test_file)

        # Delete the file
        test_file.unlink()

        # Cleanup should remove the entry
        removed = cache.cleanup_stale()

        assert removed == 1
        assert len(cache._cache) == 0

    def test_cleanup_stale_keeps_existing_files(self, tmp_path):
        """Test cleanup_stale keeps entries for existing files."""
        cache_file = tmp_path / "cache.json"
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        cache = FileHashCache(cache_file=cache_file)
        cache.load()
        cache.get_hash(test_file)

        # File still exists
        removed = cache.cleanup_stale()

        assert removed == 0
        assert len(cache._cache) == 1

    def test_context_manager_loads_and_saves(self, tmp_path):
        """Test context manager loads on enter and saves on exit."""
        cache_file = tmp_path / "cache.json"
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        with FileHashCache(cache_file=cache_file) as cache:
            assert cache.is_loaded
            cache.get_hash(test_file)

        # File should have been saved
        assert cache_file.exists()

    def test_context_manager_no_save_on_exception(self, tmp_path):
        """Test context manager doesn't save if exception occurs."""
        import json

        cache_file = tmp_path / "cache.json"
        original_data = {"version": 1}
        cache_file.write_text(json.dumps(original_data), encoding="utf-8")
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        try:
            with FileHashCache(cache_file=cache_file) as cache:
                cache.get_hash(test_file)
                msg = "Simulated error"
                raise RuntimeError(msg)
        except RuntimeError:
            pass

        # File should not have been updated with new entry
        saved_data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert str(test_file.resolve()) not in saved_data

    def test_auto_save_saves_after_modification(self, tmp_path):
        """Test auto_save mode saves after each modification."""
        cache_file = tmp_path / "cache.json"
        test_file1 = tmp_path / "test1.sto"
        test_file2 = tmp_path / "test2.sto"
        test_file1.write_bytes(b"content1")
        test_file2.write_bytes(b"content2")

        cache = FileHashCache(cache_file=cache_file, auto_save=True)
        cache.load()

        # First hash should trigger save
        cache.get_hash(test_file1)
        assert cache_file.exists()

        # Verify file was saved with first entry
        import json

        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert str(test_file1.resolve()) in data

    def test_invalidate_marks_modified(self, tmp_path):
        """Test that invalidate marks cache as modified."""
        cache_file = tmp_path / "cache.json"
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        cache = FileHashCache(cache_file=cache_file)
        cache.load()
        cache.get_hash(test_file)
        cache._modified = False  # Reset

        cache.invalidate(test_file)

        assert cache._modified

    def test_clear_marks_modified(self, tmp_path):
        """Test that clear marks cache as modified."""
        cache_file = tmp_path / "cache.json"
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        cache = FileHashCache(cache_file=cache_file)
        cache.load()
        cache.get_hash(test_file)
        cache._modified = False  # Reset

        cache.clear()

        assert cache._modified

    def test_cache_file_property(self, tmp_path):
        """Test cache_file property returns correct path."""
        cache_file = tmp_path / "cache.json"
        cache = FileHashCache(cache_file=cache_file)

        assert cache.cache_file == cache_file

    def test_default_cache_path(self):
        """Test default cache path is set correctly."""
        cache = FileHashCache()

        assert cache.cache_file == FileHashCache.DEFAULT_CACHE_PATH

    def test_is_loaded_property(self, tmp_path):
        """Test is_loaded property."""
        cache_file = tmp_path / "cache.json"
        cache = FileHashCache(cache_file=cache_file)

        assert not cache.is_loaded

        cache.load()

        assert cache.is_loaded

    def test_corrupted_json_raises_error(self, tmp_path):
        """Test that corrupted JSON raises JSONDecodeError."""
        import json

        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{ invalid json }", encoding="utf-8")

        cache = FileHashCache(cache_file=cache_file)

        with pytest.raises(json.JSONDecodeError):
            cache.load()

    def test_cache_survives_across_sessions(self, tmp_path):
        """Test that cache entries persist across sessions."""
        cache_file = tmp_path / "cache.json"
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"test content for persistence")

        # Session 1: Create cache and hash file
        with FileHashCache(cache_file=cache_file) as cache1:
            hash1 = cache1.get_hash(test_file)

        # Session 2: Load cache and verify hash is still cached
        cache2 = FileHashCache(cache_file=cache_file)
        cache2.load()

        # The entry should be in cache
        path_str = str(test_file.resolve())
        assert path_str in cache2._cache

        # Hash should match
        cached_hash, _, _ = cache2._cache[path_str]
        assert cached_hash == hash1


class TestDuplicateInfo:
    """Tests for DuplicateInfo dataclass."""

    def test_create_duplicate_info(self, tmp_path):
        """Test creating DuplicateInfo."""
        source = tmp_path / "source.sto"
        existing = tmp_path / "existing.sto"

        info = DuplicateInfo(
            source_path=source,
            existing_path=existing,
            file_hash="abc123",
            file_size=1024,
        )

        assert info.source_path == source
        assert info.existing_path == existing
        assert info.file_hash == "abc123"
        assert info.file_size == 1024


class TestDuplicateDetector:
    """Tests for DuplicateDetector class."""

    def test_init_creates_default_cache(self):
        """Test default initialization."""
        detector = DuplicateDetector()

        assert detector.hash_cache is not None
        assert isinstance(detector.hash_cache, FileHashCache)

    def test_build_index_empty_directory(self, tmp_path):
        """Test building index for empty directory."""
        detector = DuplicateDetector()
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        count = detector.build_index(empty_dir, show_progress=False)

        assert count == 0
        assert detector.indexed_count == 0

    def test_build_index_nonexistent_directory(self, tmp_path):
        """Test building index for nonexistent directory."""
        detector = DuplicateDetector()

        count = detector.build_index(tmp_path / "nonexistent", show_progress=False)

        assert count == 0

    def test_build_index_with_files(self, tmp_path):
        """Test building index with files."""
        detector = DuplicateDetector()
        (tmp_path / "file1.sto").write_bytes(b"content1")
        (tmp_path / "file2.sto").write_bytes(b"content2")

        count = detector.build_index(tmp_path, show_progress=False)

        assert count == 2
        assert detector.indexed_count == 2

    def test_build_index_with_duplicates(self, tmp_path):
        """Test building index deduplicates by hash."""
        detector = DuplicateDetector()
        dup_content = b"duplicate"
        (tmp_path / "dup1.sto").write_bytes(dup_content)
        (tmp_path / "dup2.sto").write_bytes(dup_content)

        count = detector.build_index(tmp_path, show_progress=False)

        # Should have only 1 unique hash
        assert count == 1

    def test_find_duplicate_no_match(self, tmp_path):
        """Test find_duplicate returns None when no duplicate."""
        detector = DuplicateDetector()
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "existing.sto").write_bytes(b"existing")

        detector.build_index(target_dir, show_progress=False)

        source = tmp_path / "source.sto"
        source.write_bytes(b"different content")

        result = detector.find_duplicate(source)

        assert result is None

    def test_find_duplicate_finds_match(self, tmp_path):
        """Test find_duplicate finds existing duplicate."""
        detector = DuplicateDetector()
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        content = b"same content"
        existing = target_dir / "existing.sto"
        existing.write_bytes(content)

        detector.build_index(target_dir, show_progress=False)

        source = tmp_path / "source.sto"
        source.write_bytes(content)

        result = detector.find_duplicate(source)

        assert result is not None
        assert isinstance(result, DuplicateInfo)
        assert result.source_path == source
        assert result.existing_path == existing.resolve()
        assert result.file_size == len(content)

    def test_find_duplicate_ignores_same_file(self, tmp_path):
        """Test find_duplicate doesn't report file as its own duplicate."""
        detector = DuplicateDetector()
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        existing = target_dir / "file.sto"
        existing.write_bytes(b"content")

        detector.build_index(target_dir, show_progress=False)

        result = detector.find_duplicate(existing)

        assert result is None

    def test_find_duplicate_by_hash_no_match(self, tmp_path):
        """Test find_duplicate_by_hash returns None when no match."""
        detector = DuplicateDetector()
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "existing.sto").write_bytes(b"existing")

        detector.build_index(target_dir, show_progress=False)

        result = detector.find_duplicate_by_hash("nonexistent_hash", 100)

        assert result is None

    def test_find_duplicate_by_hash_finds_match(self, tmp_path):
        """Test find_duplicate_by_hash finds existing duplicate."""
        detector = DuplicateDetector()
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        content = b"existing content"
        existing = target_dir / "existing.sto"
        existing.write_bytes(content)

        detector.build_index(target_dir, show_progress=False)

        content_hash = hashlib.sha256(content).hexdigest()
        result = detector.find_duplicate_by_hash(content_hash, len(content))

        assert result is not None
        assert result == existing.resolve()

    def test_is_duplicate_true(self, tmp_path):
        """Test is_duplicate returns True for identical files."""
        detector = DuplicateDetector()
        content = b"identical content"
        file1 = tmp_path / "file1.sto"
        file2 = tmp_path / "file2.sto"
        file1.write_bytes(content)
        file2.write_bytes(content)

        result = detector.is_duplicate(file1, file2)

        assert result is True

    def test_is_duplicate_false(self, tmp_path):
        """Test is_duplicate returns False for different files."""
        detector = DuplicateDetector()
        file1 = tmp_path / "file1.sto"
        file2 = tmp_path / "file2.sto"
        file1.write_bytes(b"content one")
        file2.write_bytes(b"content two")

        result = detector.is_duplicate(file1, file2)

        assert result is False

    def test_is_duplicate_file_not_found(self, tmp_path):
        """Test is_duplicate returns False if file doesn't exist."""
        detector = DuplicateDetector()
        file1 = tmp_path / "file1.sto"
        file1.write_bytes(b"content")
        nonexistent = tmp_path / "nonexistent.sto"

        result = detector.is_duplicate(file1, nonexistent)

        assert result is False

    def test_add_to_index(self, tmp_path):
        """Test add_to_index adds file to index."""
        detector = DuplicateDetector()
        detector.build_index(tmp_path, show_progress=False)

        new_file = tmp_path / "new.sto"
        new_file.write_bytes(b"new content")

        file_hash = detector.add_to_index(new_file)

        assert detector.indexed_count == 1
        assert file_hash == hashlib.sha256(b"new content").hexdigest()

    def test_add_to_index_no_duplicate_addition(self, tmp_path):
        """Test add_to_index doesn't add duplicate hashes."""
        detector = DuplicateDetector()
        content = b"same content"
        file1 = tmp_path / "file1.sto"
        file2 = tmp_path / "file2.sto"
        file1.write_bytes(content)
        file2.write_bytes(content)

        detector.build_index(tmp_path, show_progress=False)
        # file1 should be indexed
        initial_count = detector.indexed_count

        # Adding file2 with same content shouldn't increase count
        detector.add_to_index(file2)

        assert detector.indexed_count == initial_count

    def test_remove_from_index(self, tmp_path):
        """Test remove_from_index removes file."""
        detector = DuplicateDetector()
        test_file = tmp_path / "test.sto"
        test_file.write_bytes(b"content")

        detector.build_index(tmp_path, show_progress=False)
        assert detector.indexed_count == 1

        detector.remove_from_index(test_file)

        assert detector.indexed_count == 0

    def test_indexed_directory_property(self, tmp_path):
        """Test indexed_directory returns correct value."""
        detector = DuplicateDetector()

        assert detector.indexed_directory is None

        detector.build_index(tmp_path, show_progress=False)

        assert detector.indexed_directory == tmp_path.resolve()


class TestDuplicateDetectorIntegration:
    """Integration tests for DuplicateDetector."""

    def test_full_workflow(self, tmp_path):
        """Test complete duplicate detection workflow."""
        # Setup target directory with existing files
        target = tmp_path / "target"
        target.mkdir()
        (target / "car1" / "track1").mkdir(parents=True)
        existing = target / "car1" / "track1" / "setup.sto"
        existing.write_bytes(b"setup content")

        # Setup source directory
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        duplicate = source_dir / "new_setup.sto"
        duplicate.write_bytes(b"setup content")
        unique = source_dir / "unique_setup.sto"
        unique.write_bytes(b"unique content")

        # Initialize detector
        detector = DuplicateDetector()
        detector.build_index(target, show_progress=False)

        # Check files
        dup_result = detector.find_duplicate(duplicate)
        unique_result = detector.find_duplicate(unique)

        assert dup_result is not None
        assert dup_result.existing_path == existing.resolve()
        assert unique_result is None

    def test_rebuild_index_clears_old(self, tmp_path):
        """Test rebuilding index clears old entries."""
        detector = DuplicateDetector()

        # First index
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        (dir1 / "file1.sto").write_bytes(b"content1")
        detector.build_index(dir1, show_progress=False)
        assert detector.indexed_count == 1

        # Rebuild with different directory
        dir2 = tmp_path / "dir2"
        dir2.mkdir()
        (dir2 / "file2.sto").write_bytes(b"content2")
        (dir2 / "file3.sto").write_bytes(b"content3")
        detector.build_index(dir2, show_progress=False)

        assert detector.indexed_count == 2
        assert detector.indexed_directory == dir2.resolve()

    def test_hash_content_before_write(self, tmp_path):
        """Test checking hash before writing (download scenario)."""
        detector = DuplicateDetector()
        target = tmp_path / "target"
        target.mkdir()
        content = b"existing setup content"
        (target / "existing.sto").write_bytes(content)

        detector.build_index(target, show_progress=False)

        # Simulate download: hash content before writing
        download_content = b"existing setup content"
        content_hash = detector.hash_cache.compute_hash_from_bytes(download_content)
        existing = detector.find_duplicate_by_hash(content_hash, len(download_content))

        assert existing is not None
        assert existing.name == "existing.sto"
