#
# Copyright(c) 2012-2021 Intel Corporation
# Copyright(c) 2025 Huawei Technologies Co., Ltd.
# Copyright(c) 2025 Liyi Meng
# SPDX-License-Identifier: BSD-3-Clause
#

import pytest
import unittest.mock as mock
import stat

import helpers as h
import opencas


# Tests for is_regular_file


@mock.patch("os.stat")
def test_is_regular_file_true(mock_stat):
    mock_stat.return_value = mock.Mock(st_mode=stat.S_IFREG)
    assert opencas.is_regular_file("/tmp/cache.img") is True


@mock.patch("os.stat")
def test_is_regular_file_false_block_device(mock_stat):
    mock_stat.return_value = mock.Mock(st_mode=stat.S_IFBLK)
    assert opencas.is_regular_file("/dev/sda") is False


@mock.patch("os.stat")
def test_is_regular_file_false_directory(mock_stat):
    mock_stat.return_value = mock.Mock(st_mode=stat.S_IFDIR)
    assert opencas.is_regular_file("/tmp/somedir") is False


@mock.patch("os.stat")
def test_is_regular_file_oserror(mock_stat):
    mock_stat.side_effect = OSError()
    assert opencas.is_regular_file("/nonexistent/file") is False


# Tests for setup_loopback


@mock.patch("opencas.is_regular_file")
@mock.patch("subprocess.run")
def test_setup_loopback_success(mock_run, mock_is_file):
    mock_is_file.return_value = True
    mock_run.return_value = h.get_process_mock(0, "/dev/loop0\n", "")

    result = opencas.setup_loopback("/tmp/cache.img")

    assert result == "/dev/loop0"
    mock_run.assert_called_once_with(
        ["losetup", "--find", "--show", "/tmp/cache.img"],
        stdout=mock.ANY,
        stderr=mock.ANY,
        universal_newlines=True,
    )


@mock.patch("opencas.is_regular_file")
def test_setup_loopback_not_a_file(mock_is_file):
    mock_is_file.return_value = False

    with pytest.raises(ValueError, match="is not a regular file"):
        opencas.setup_loopback("/dev/sda")


@mock.patch("opencas.is_regular_file")
@mock.patch("subprocess.run")
def test_setup_loopback_losetup_failure(mock_run, mock_is_file):
    mock_is_file.return_value = True
    mock_run.return_value = h.get_process_mock(1, "", "losetup: failed")

    with pytest.raises(RuntimeError, match="Failed to set up loopback"):
        opencas.setup_loopback("/tmp/cache.img")


@mock.patch("opencas.is_regular_file")
@mock.patch("subprocess.run")
def test_setup_loopback_empty_output(mock_run, mock_is_file):
    mock_is_file.return_value = True
    mock_run.return_value = h.get_process_mock(0, "", "")

    with pytest.raises(RuntimeError, match="losetup returned empty device"):
        opencas.setup_loopback("/tmp/cache.img")


# Tests for teardown_loopback


@mock.patch("subprocess.run")
def test_teardown_loopback_success(mock_run):
    mock_run.return_value = h.get_process_mock(0, "", "")

    opencas.teardown_loopback("/dev/loop0")

    mock_run.assert_called_once_with(
        ["losetup", "-d", "/dev/loop0"],
        stdout=mock.ANY,
        stderr=mock.ANY,
        universal_newlines=True,
    )


@mock.patch("subprocess.run")
def test_teardown_loopback_failure(mock_run):
    mock_run.return_value = h.get_process_mock(1, "", "losetup: /dev/loop0: not found")

    with pytest.raises(RuntimeError, match="Failed to detach loopback"):
        opencas.teardown_loopback("/dev/loop0")


# Tests for check_block_device accepting regular files


@mock.patch("os.path.exists")
@mock.patch("os.stat")
def test_check_block_device_accepts_regular_file(mock_stat, mock_path_exists):
    mock_path_exists.side_effect = h.get_mock_os_exists(["/tmp/cache.img"])
    mock_stat.return_value = mock.Mock(st_mode=stat.S_IFREG)

    # Should not raise
    opencas.cas_config.check_block_device("/tmp/cache.img")


@mock.patch("os.path.exists")
@mock.patch("os.stat")
def test_check_block_device_accepts_block_device(mock_stat, mock_path_exists):
    mock_path_exists.side_effect = h.get_mock_os_exists(["/dev/sda"])
    mock_stat.return_value = mock.Mock(st_mode=stat.S_IFBLK)

    # Should not raise
    opencas.cas_config.check_block_device("/dev/sda")


@mock.patch("os.path.exists")
@mock.patch("os.stat")
def test_check_block_device_rejects_directory(mock_stat, mock_path_exists):
    mock_path_exists.side_effect = h.get_mock_os_exists(["/home/user/stuff"])
    mock_stat.return_value = mock.Mock(st_mode=stat.S_IFDIR)

    with pytest.raises(ValueError, match="is not a block device or regular file"):
        opencas.cas_config.check_block_device("/home/user/stuff")


# Tests for start_cache with file-backed loopback


@mock.patch("opencas.casadm.start_cache")
@mock.patch("opencas.setup_loopback")
@mock.patch("opencas.is_regular_file")
def test_start_cache_with_file(mock_is_file, mock_setup_loop, mock_start_cache):
    mock_is_file.return_value = True
    mock_setup_loop.return_value = "/dev/loop0"

    cache = opencas.cas_config.cache_config(
        cache_id="1", device="/tmp/cache.img", cache_mode="WT"
    )

    opencas.start_cache(cache, load=False)

    mock_setup_loop.assert_called_once_with("/tmp/cache.img")
    mock_start_cache.assert_called_once_with(
        device="/dev/loop0",
        cache_id=1,
        cache_mode="wt",
        cache_line_size=None,
        load=False,
        force=False,
    )


@mock.patch("opencas.casadm.start_cache")
@mock.patch("opencas.setup_loopback")
@mock.patch("opencas.is_regular_file")
def test_start_cache_with_block_device(mock_is_file, mock_setup_loop, mock_start_cache):
    mock_is_file.return_value = False

    cache = opencas.cas_config.cache_config(
        cache_id="1", device="/dev/sda", cache_mode="WT"
    )

    opencas.start_cache(cache, load=False)

    mock_setup_loop.assert_not_called()
    mock_start_cache.assert_called_once_with(
        device="/dev/sda",
        cache_id=1,
        cache_mode="wt",
        cache_line_size=None,
        load=False,
        force=False,
    )


# Tests for add_core with file-backed loopback


@mock.patch("opencas.casadm.add_core")
@mock.patch("opencas.setup_loopback")
@mock.patch("opencas.is_regular_file")
def test_add_core_with_file(mock_is_file, mock_setup_loop, mock_add_core):
    mock_is_file.return_value = True
    mock_setup_loop.return_value = "/dev/loop1"

    core = opencas.cas_config.core_config(
        cache_id="1", core_id="1", path="/tmp/backing.img"
    )

    opencas.add_core(core, attach=False)

    mock_setup_loop.assert_called_once_with("/tmp/backing.img")
    mock_add_core.assert_called_once_with(
        device="/dev/loop1",
        cache_id=1,
        core_id=1,
        try_add=False,
    )


@mock.patch("opencas.casadm.add_core")
@mock.patch("opencas.setup_loopback")
@mock.patch("opencas.is_regular_file")
def test_add_core_with_block_device(mock_is_file, mock_setup_loop, mock_add_core):
    mock_is_file.return_value = False

    core = opencas.cas_config.core_config(
        cache_id="1", core_id="1", path="/dev/sdb"
    )

    opencas.add_core(core, attach=False)

    mock_setup_loop.assert_not_called()
    mock_add_core.assert_called_once_with(
        device="/dev/sdb",
        cache_id=1,
        core_id=1,
        try_add=False,
    )


# Tests for cache_config and core_config accepting file paths


@mock.patch("os.path.exists")
@mock.patch("os.stat")
@mock.patch("subprocess.run")
def test_cache_config_from_line_device_is_regular_file(
    mock_run, mock_stat, mock_path_exists
):
    mock_path_exists.side_effect = h.get_mock_os_exists(["/tmp/cache.img"])
    mock_stat.return_value = mock.Mock(st_mode=stat.S_IFREG)
    mock_run.return_value = h.get_process_mock(0, "cache.img\n", "")

    # Should not raise - regular files are now accepted
    opencas.cas_config.cache_config.from_line("1    /tmp/cache.img    WT")


@mock.patch("os.path.exists")
@mock.patch("os.stat")
def test_core_config_from_line_device_is_regular_file(mock_stat, mock_path_exists):
    mock_path_exists.side_effect = h.get_mock_os_exists(["/tmp/backing.img"])
    mock_stat.return_value = mock.Mock(st_mode=stat.S_IFREG)

    # Should not raise - regular files are now accepted
    opencas.cas_config.core_config.from_line("1    1    /tmp/backing.img")


# Test standby cache with file-backed loopback


@mock.patch("opencas.casadm.start_standby_cache")
@mock.patch("opencas.setup_loopback")
@mock.patch("opencas.is_regular_file")
def test_start_standby_cache_with_file(mock_is_file, mock_setup_loop, mock_start_standby):
    mock_is_file.return_value = True
    mock_setup_loop.return_value = "/dev/loop0"

    cache = opencas.cas_config.cache_config(
        cache_id="1", device="/tmp/cache.img", cache_mode="WT",
        target_failover_state="standby"
    )

    opencas.start_cache(cache, load=False)

    mock_setup_loop.assert_called_once_with("/tmp/cache.img")
    mock_start_standby.assert_called_once_with(
        device="/dev/loop0",
        cache_id=1,
        cache_line_size=None,
        load=False,
        force=False,
    )
