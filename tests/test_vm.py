#!/usr/bin/py.test

import os, os.path, sys, tempfile, time

import py.test

import _support
import pyvix_test_site_config as site_config
from pyvix.vix import *

def _openGenericVM():
    h = Host()
    vm = _reopenGenericVMOnHost(h)
    return h, vm


def _reopenGenericVMOnHost(h):
    return h.openVM(_support.site_config.generic_vmx)

def test_VM_creation_delHostFirst():
    h, vm = _openGenericVM()
    assert vm.host is h
    del h
    assert vm.host is not None
    del vm

def test_VM_creation_delVMFirst():
    h, vm = _openGenericVM()
    assert vm.host is h
    del vm
    del h

def test_VM_vmxPath():
    h, vm = _openGenericVM()
    assert vm.vmxPath == site_config.generic_vmx

def test_VM_propertyRetrieval():
    # XXX: Ought to expand this test.
    h, vm = _openGenericVM()
    vm[VIX_PROPERTY_VM_POWER_STATE]
    vm[VIX_PROPERTY_VM_VMX_PATHNAME]

def test_VM_close_explicit_delHostFirst():
    h, vm = _openGenericVM()
    assert not vm.closed
    assert vm.host is h
    del h
    vm.close()
    # At this point, host has been destroyed.
    assert vm.closed
    assert vm.host is None
    py.test.raises(VIXClientProgrammerError, vm.close)
    del vm

def test_VM_close_explicit_delVMFirst():
    h, vm = _openGenericVM()
    assert not vm.closed
    assert vm.host is h
    vm.close()
    # At this point, host is still alive, but is no longer associated with vm.
    assert vm.closed
    assert vm.host is None
    py.test.raises(VIXClientProgrammerError, vm.close)
    del vm
    del h

def test_Host_close_explicit_withOpenVM():
    h, vm = _openGenericVM()
    assert not vm.closed
    assert vm.host is h
    h.close()
    # Closing a Host should close all of its open VM objects as a side effect:
    assert vm.closed
    assert vm.host is None

def test_VM_powerOnPowerOffAndSuspend(actionWhilePoweredOn=None):
    # XXX: TODO: not all this test needs to be skipped, just the
    # suspend+poweron part.
    if site_config.skip_tests_that_end_in_segmentation_fault:
        return None
    h, vm = _openGenericVM()

    # If the VM is already powered off, it should object to an attempt to power
    # it off:
    if vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_POWERED_OFF != 0:
        print 'VM was initially powered off.'
        py.test.raises(VIXException, vm.powerOff)
    else:
        print 'VM was initially powered on; will now power it off...'
        vm.powerOff()
        print 'VM powered off.'

    assert vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_POWERED_OFF != 0
    print 'Powering on VM...'
    vm.powerOn()
    print 'VM powered on; waiting for signal from VMWare Tools that operating',
    print ' system has booted...'
    vm.waitForToolsInGuest()
    print 'VM operating system booted.'
    assert vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_POWERED_OFF == 0

    shouldPowerOffAtEnd = True
    if actionWhilePoweredOn is not None:
        print 'Invoking intermediate action...'
        shouldPowerOffAtEnd = actionWhilePoweredOn(vm)
        print 'Intermediate action finished.'

    if not shouldPowerOffAtEnd:
        print 'Not powering off VM at end.'
    else:
        if actionWhilePoweredOn is None:
            print 'Suspending VM...'
            vm.suspend()
            print 'VM suspended.'
            print 'Powering VM back on after suspension...'
            vm.powerOn()
            print 'VM powered on; waiting for signal from VMWare Tools that',
            print ' operating system has booted...'
            vm.waitForToolsInGuest()
            print 'VM operating system booted after suspension; will wait 5',
            print ' seconds so you can observe this.'
            time.sleep(5)

        print 'Powering VM off at end...'
        vm.powerOff()
        print 'VM powered off.'
        assert vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_POWERED_OFF != 0

def test_VM_installToolsInGuest_whenToolsAreAlreadyPresent():
    def actionWhilePoweredOn(vm):
        vm.installTools()
        return True

    test_VM_powerOnPowerOffAndSuspend(actionWhilePoweredOn)

def test_VM_reset():
    def actionWhilePoweredOn(vm):
        assert (
               vm[VIX_PROPERTY_VM_POWER_STATE]
            & (VIX_POWERSTATE_POWERED_ON | VIX_POWERSTATE_TOOLS_RUNNING)
            != 0
          )
        assert vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_RESETTING == 0
        vm.reset()
        # We can't make any assertion such as:
        #   vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_RESETTING != 0
        # because there are no guarantees about the relationship between this
        # client program's execution and the progress of resetting the VM.

        vm.waitForToolsInGuest()
        assert (
               vm[VIX_PROPERTY_VM_POWER_STATE]
            & (VIX_POWERSTATE_POWERED_ON | VIX_POWERSTATE_TOOLS_RUNNING)
            != 0
          )

        return True

    test_VM_powerOnPowerOffAndSuspend(actionWhilePoweredOn)

def test_snapshotOps():
    h, vm = _openGenericVM()

    print 'Initially, the VM had %d snapshots.' % vm.nRootSnapshots

    if vm.nRootSnapshots > 0:
        snaps = vm.rootSnapshots
        assert not snaps[0].closed
        assert snaps[0].vm is vm
        vm.close()
        # Closing a VM should close all of its open Snapshot objects as a side
        # effect:
        assert snaps[0].closed
        assert snaps[0].vm is None
        del snaps

        vm = _reopenGenericVMOnHost(h)
        assert vm.host is h

        if vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_POWERED_ON != 0:
            vm.powerOff()

        snaps = vm.rootSnapshots
        # Remove all existing snapshots:
        for i, s in enumerate(snaps):
            print 'Removing initial snapshot #%d' % (i + 1)
            vm.removeSnapshot(s)
            print 'Removed initial snapshot #%d' % (i + 1)

    snapname = 'snapName'
    print 'Creating named snapshot...'
    s = vm.createSnapshot(name=snapname)

    print 'Powerring off...'
    if vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_POWERED_ON != 0:
        vm.powerOff()
    ss = vm.getNamedSnapshot(snapname)
    if None == ss:
        print '---> no snapshot named ', snapname
    else:
        assert not ss.closed
        assert ss.vm is vm
        ss.close()

    print 'Removing named snapshot...'
    vm.removeSnapshot(s)
    s.close()

    print 'Creating snapshot...'
    s = vm.createSnapshot()
    print 'Snapshot created; VM now has %d snapshots.' % vm.nRootSnapshots
    assert not s.closed
    assert s.vm is vm
    nRootSnapshotsAfterCreation = vm.nRootSnapshots
    assert nRootSnapshotsAfterCreation > 0

    print 'Reverting to snapshot...'
    vm.revertToSnapshot(s)
    print 'Reverted to snapshot.'

    print 'Getting current snapshot...'
    curSnap = vm.getCurrentSnapshot()
    assert not curSnap.closed
    assert curSnap.vm is vm
    curSnap.close()

    assert not s.closed
    assert s.vm is vm

    print 'Removing snapshot...'
    vm.removeSnapshot(s)
    print 'Removed snapshot; VM now has %d snapshots.' % vm.nRootSnapshots
    assert not s.closed
    assert s.vm is vm
    assert vm.nRootSnapshots == nRootSnapshotsAfterCreation - 1

    # Even though the snapshot has been removed, the object that represents it
    # is still considered "open", so we should be able to explicitly close it.
    s.close()
    # Another attempt to close s should fail:
    py.test.raises(VIXClientProgrammerError, s.close)

def test_VM_upgradeVirtualHardware():
    h, vm = _openGenericVM()

    if vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_POWERED_OFF == 0:
        print 'VM was initially powered on; will now power it off...'
        vm.powerOff()
        print 'VM powered off.'

    if site_config.hardware_is_upgradable:
        vm.upgradeVirtualHardware()
    else:
        print 'Calling upgradeVirtualHardware...'
        py.test.raises(VIXException, vm.upgradeVirtualHardware)
        print 'upgradeVirtualHardware complete.'



def _callback(param):
    print '--> Callback successfully called. Param is:', param

def test_VM_loginInGuest_plusCopyAndRun():
    h, vm = _openGenericVM()

    if vm[VIX_PROPERTY_VM_POWER_STATE] & VIX_POWERSTATE_POWERED_ON == 0:
        print 'Powering on VM...'
        vm.powerOn()
        print 'Waiting for OS boot...'
        vm.waitForToolsInGuest()
        print 'OS booted.'

    print 'Logging into guest...'
    py.test.raises(VIXSecurityException,
        vm.loginInGuest, 'BOGUS_ACCOUNT', 'pass'
      )
    py.test.raises(VIXSecurityException,
        vm.loginInGuest, 'Administrator', 'BOGUS_PASSWORD'
      )
    vm.loginInGuest(site_config.guest_username, site_config.guest_password)
    print 'Logged into guest.'

    # Copy an innocuous test file from the host to the guest, execute it, then
    # copy it back to the host and verify its presence and contents.
    DUMMY_PROGRAM_FN = site_config.guest_test_execution_program
    DUMMY_PROGRAM_SOURCE_PATH_HOST = os.path.join(
        os.path.dirname(__file__), 'data', DUMMY_PROGRAM_FN
      )
    DUMMY_PROGRAM_DEST_PATH_HOST = os.path.join(
        tempfile.gettempdir(), DUMMY_PROGRAM_FN
      )
    if os.path.exists(DUMMY_PROGRAM_DEST_PATH_HOST):
        os.remove(DUMMY_PROGRAM_DEST_PATH_HOST)

    DUMMY_PROGRAM_PATH_GUEST = site_config.guest_dest_dir + DUMMY_PROGRAM_FN

    print 'Copying dummy program to guest...'
    vm.copyFileFromHostToGuest(
        DUMMY_PROGRAM_SOURCE_PATH_HOST, DUMMY_PROGRAM_PATH_GUEST
      )


    print 'Running dummy program on guest - no kwargs'
    vm.runProgramInGuest(DUMMY_PROGRAM_PATH_GUEST, 'David Rushby')
    print 'Running dummy program on guest - with kwargs'
    vm.runProgramInGuest(prog=DUMMY_PROGRAM_PATH_GUEST, progArg='some')
    print 'Running dummy program on guest - with options=VIX_RUNPROGRAM_RETURN_IMMEDIATELY'
    vm.runProgramInGuest(prog=DUMMY_PROGRAM_PATH_GUEST, progArg='random',   options=VIX_RUNPROGRAM_RETURN_IMMEDIATELY)
    print 'Running dummy program on guest - with options=VIX_RUNPROGRAM_RETURN_IMMEDIATELY and callback'
    vm.runProgramInGuest(prog=DUMMY_PROGRAM_PATH_GUEST, progArg='cmdline',  options=VIX_RUNPROGRAM_RETURN_IMMEDIATELY, cback=_callback)
    print 'Running dummy program on guest - with options=VIX_RUNPROGRAM_RETURN_IMMEDIATELY and callback and callbackArg'
    vm.runProgramInGuest(prog=DUMMY_PROGRAM_PATH_GUEST, progArg='argument', options=VIX_RUNPROGRAM_RETURN_IMMEDIATELY, cback=_callback, cbackArg='Super cbackArg')
    print 'Running dummy program on guest - with zero options=0, callback and callbackArg'
    vm.runProgramInGuest(prog=DUMMY_PROGRAM_PATH_GUEST, progArg='argument', options=0, cback=_callback, cbackArg='Super cbackArg')



    assert not os.path.exists(DUMMY_PROGRAM_DEST_PATH_HOST)
    print 'Copying dummy program back from guest to host...'
    vm.copyFileFromGuestToHost(DUMMY_PROGRAM_PATH_GUEST,
        DUMMY_PROGRAM_DEST_PATH_HOST
      )
    assert os.path.exists(DUMMY_PROGRAM_DEST_PATH_HOST)

    print 'Verifying contents of transferred file...'
    srcContents = file(DUMMY_PROGRAM_SOURCE_PATH_HOST, 'rb').read()
    destContents = file(DUMMY_PROGRAM_DEST_PATH_HOST, 'rb').read()
    assert srcContents == destContents

    print 'Removing dummy file from temporary desination on host...'
    os.remove(DUMMY_PROGRAM_DEST_PATH_HOST)
