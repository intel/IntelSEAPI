import os
from sea_runtool import default_tree, Callbacks, Progress, TaskCombiner, ProgressConst, TaskTypes

class ETWXML:
    def __init__(self, callback, providers):
        self.callback = callback
        self.providers = providers

    def tag_name(self, tag):
        if tag[0] == '{':
            return tag.split('}')[1]
        return tag

    def iterate_events(self, file):
        try:
            import xml.etree.cElementTree as ET
        except:
            import xml.etree.ElementTree as ET
        level = 0
        for event, elem in ET.iterparse(file, events=('start', 'end')):
            if event == 'start':
                level += 1
            else:
                if level == 2:
                    yield elem
                    elem.clear()
                level -= 1

    def as_dict(self, elem):
        return dict((self.tag_name(child.tag), child) for child in elem.getchildren())

    def parse_system(self, system):
        res = {}
        system = self.as_dict(system)
        if not system:
            return res
        if system.has_key('TimeCreated'):
            time_created = system['TimeCreated']
            res['time'] = time_created.attrib['RawTime']
        if system.has_key('Task'):
            task = system['Task']
            res['Task'] = task.text
        if system.has_key('EventID'):
            EventID = system['EventID']
            res['EventID'] = EventID.text
        if system.has_key('Opcode'):
            Opcode = system['Opcode']
            res['Opcode'] = Opcode.text
        provider = system['Provider']
        execution = system['Execution'] if system.has_key('Execution') else None
        res['provider'] = provider.attrib['Name'] if provider.attrib.has_key('Name') else provider.attrib['Guid'] if provider.attrib.has_key('Guid') else None
        if execution != None:
            res['pid'] = execution.attrib['ProcessID']
            res['tid'] = execution.attrib['ThreadID']
            res['cpu'] = execution.attrib['ProcessorID']
        return res

    def parse_event_data(self, data):
        res = {}
        for child in data.getchildren():
            if 'ComplexData' == self.tag_name(child.tag):
                res[child.attrib['Name']] = self.parse_event_data(child)
            else:
                res[child.attrib['Name']] = child.text.strip() if child.text else ""
        return res

    def parse_rendering_info(self, info):
        res = {}
        info = self.as_dict(info)
        for key, data in info.iteritems():
            res[key] = data.text.strip() if data.text else ""
        return res

    def parse(self, file):
        unhandled_providers = set()
        for elem in self.iterate_events(file):
            children = self.as_dict(elem)
            if not children:
                continue
            system = self.parse_system(children['System'])
            if not system:
                continue
            if system['provider'] in self.providers:
                if children.has_key('BinaryEventData'):
                    self.callback(system, children['BinaryEventData'].text, self.as_dict(children['ExtendedTracingInfo'])['EventGuid'].text)
                else:
                    data = self.parse_event_data(children['EventData']) if children.has_key('EventData') else None
                    info = self.parse_rendering_info(children['RenderingInfo']) if children.has_key('RenderingInfo') else None
                    self.callback(system, data, info)
            else:
                if system['provider'] not in unhandled_providers:
                    unhandled_providers.add(system['provider'])
        return unhandled_providers


DMA_PACKET_TYPE = ["CLIENT_RENDER", "CLIENT_PAGING", "SYSTEM_PAGING", "SYSTEM_PREEMTION"]
QUEUE_PACKET_TYPE = ["RENDER", "DEFERRED", "SYSTEM", "MMIOFLIP", "WAIT", "SIGNAL", "DEVICE", "SOFTWARE", "PAGING"]
QUANTUM_STATUS = ["READY", "RUNNING", "EXPIRED", "PROCESSED_EXPIRE"]
FUN_NAMES = {0: 'DriverEntry', 1: 'DxgkCreateClose', 2: 'DxgkInternalDeviceIoctl', 2051: 'DxgkCreateKeyedMutex', 2052: 'DxgkOpenKeyedMutex', 2053: 'DxgkDestroyKeyedMutex', 2054: 'DxgkAcquireKeyedMutex', 2049: 'DxgkQueryStatistics', 2056: 'DxgkConfigureSharedResource', 2057: 'DxgkGetOverlayState', 2058: 'DxgkCheckVidPnExclusiveOwnership', 2059: 'DxgkCheckSharedResourceAccess', 2060: 'DxgkGetPresentHistory', 2050: 'DxgkOpenSynchronizationObject', 2062: 'DxgkDestroyOutputDupl', 2063: 'DxgkOutputDuplGetFrameInfo', 2064: 'DxgkOutputDuplGetMetaData', 2065: 'DxgkOutputDuplGetPointerShapeData', 2066: 'DxgkCreateKeyedMutex2', 2067: 'DxgkOpenKeyedMutex2', 2068: 'DxgkAcquireKeyedMutex2', 2069: 'DxgkReleaseKeyedMutex2', 2070: 'DxgkOfferAllocations', 2071: 'DxgkReclaimAllocations', 2072: 'DxgkOutputDuplReleaseFrame', 2073: 'DxgkQueryResourceInfoFromNtHandle', 2074: 'DxgkShareObjects', 2075: 'DxgkOpenNtHandleFromName', 2076: 'DxgkOpenResourceFromNtHandle', 2077: 'DxgkSetVidPnSourceOwner1', 2078: 'DxgkEnumAdapters', 2079: 'DxgkPinDirectFlipResources', 2080: 'DxgkUnpinDirectFlipResources', 2081: 'DxgkGetPathsModality', 2082: 'DxgkOpenAdapterFromLuid', 2083: 'DxgkWaitForVerticalBlankEvent2', 2084: 'DxgkSetContextInProcessSchedulingPriority', 2085: 'DxgkGetContextInProcessSchedulingPriority', 2086: 'DxgkOpenSyncObjectFromNtHandle', 2087: 'DxgkNotifyProcessFreezeCallout', 2088: 'DxgkGetSharedResourceAdapterLuid', 2089: 'DxgkSetStereoEnabled', 2090: 'DxgkGetCachedHybridQueryValue', 2055: 'DxgkReleaseKeyedMutex', 2092: 'DxgkPresentMultiPlaneOverlay', 2093: 'DxgkCheckMultiPlaneOverlaySupport', 2094: 'DxgkSetIndependentFlipMode', 2095: 'DxgkConfirmToken', 2096: 'DxgkNotifyProcessThawCallout', 2097: 'DxgkSetPresenterViewMode', 2098: 'DxgkReserveGpuVirtualAddress', 2099: 'DxgkFreeGpuVirtualAddress', 2100: 'DxgkMapGpuVirtualAddress', 2101: 'DxgkCreateContextVirtual', 2102: 'DxgkSubmitCommand', 2103: 'DxgkLock2', 2104: 'DxgkUnlock2', 2105: 'DxgkDestroyAllocation2', 2106: 'DxgkUpdateGpuVirtualAddress', 2107: 'DxgkCheckMultiPlaneOverlaySupport2', 2108: 'DxgkCreateSwapChain', 2109: 'DxgkOpenSwapChain', 2110: 'DxgkDestroySwapChain', 2111: 'DxgkAcquireSwapChain', 2112: 'DxgkReleaseSwapChain', 2113: 'DxgkAbandonSwapChain', 2114: 'DxgkSetDodIndirectSwapchain', 2115: 'DxgkMakeResident', 2116: 'DxgkEvict', 2117: 'DxgkCreatePagingQueue', 2048: 'DxgkSetDisplayPrivateDriverFormat', 2119: 'DxgkQueryVideoMemoryInfo', 2120: 'DxgkChangeVideoMemoryReservation', 2121: 'DxgkGetSwapChainMetadata', 2122: 'DxgkInvalidateCache', 2123: 'DxgkGetResourcePresentPrivateDriverData', 2124: 'DxgkSetStablePowerState', 2125: 'DxgkQueryClockCalibration', 2061: 'DxgkCreateOutputDupl', 2130: 'DxgkSetVidPnSourceHwProtection', 2131: 'DxgkMarkDeviceAsError', 2091: 'DxgkCacheHybridQueryValue', 7054: 'DmmMiniportInterfaceGetMonitorFrequencyRangeSet', 2118: 'DxgkDestroyPagingQueue', 2127: 'DxgkAdjustFullscreenGamma', 14001: 'VidMmRecalculateBudgets', 13000: 'DxgkDdiMiracastQueryCaps', 13001: 'DxgkDdiMiracastCreateContext', 13002: 'DxgkDdiMiracastIoControl', 13003: 'DxgkDdiMiracastDestroyContext', 13050: 'DxgkCbSendUserModeMessage', 13100: 'MiracastUmdDriverCreateMiracastContext', 13101: 'MiracastUmdDriverDestroyMiracastContext', 13102: 'MiracastUmdDriverStartMiracastSession', 13103: 'MiracastUmdDriverStopMiracastSession', 13104: 'MiracastUmdDriverHandleKernelModeMessage', 7000: 'DmmMiniportInterfaceGetNumSourceModes', 7001: 'DmmMiniportInterfaceAcquireFirstSourceMode', 7002: 'DmmMiniportInterfaceAcquireNextSourceMode', 7003: 'DmmMiniportInterfaceAcquirePinnedSourceMode', 7004: 'DmmMiniportInterfaceReleaseSourceMode', 7005: 'DmmMiniportInterfaceCreateNewSourceMode', 7006: 'DmmMiniportInterfaceAddSourceMode', 7007: 'DmmMiniportInterfacePinSourceMode', 7008: 'DmmMiniportInterfaceGetNumTargetModes', 7009: 'DmmMiniportInterfaceAcquireFirstTargetMode', 7010: 'DmmMiniportInterfaceAcquireNextTargetMode', 7011: 'DmmMiniportInterfaceAcquirePinnedTargetMode', 7012: 'DmmMiniportInterfaceReleaseTargetMode', 7013: 'DmmMiniportInterfaceCreateNewTargetMode', 7014: 'DmmMiniportInterfaceAddTargetMode', 7015: 'DmmMiniportInterfacePinTargetMode', 7016: 'DmmMiniportInterfaceGetNumMonitorSourceModes', 7017: 'DmmMiniportInterfaceAcquirePreferredMonitorSourceMode', 7018: 'DmmMiniportInterfaceAcquireFirstMonitorSourceMode', 7019: 'DmmMiniportInterfaceAcquireNextMonitorSourceMode', 7020: 'DmmMiniportInterfaceCreateNewMonitorSourceMode', 7021: 'DmmMiniportInterfaceAddMonitorSourceMode', 7022: 'DmmMiniportInterfaceReleaseMonitorSourceMode', 7023: 'DmmMiniportInterfaceGetNumMonitorFrequencyRanges', 7024: 'DmmMiniportInterfaceAcquireFirstMonitorFrequencyRange', 7025: 'DmmMiniportInterfaceAcquireNextMonitorFrequencyRange', 7026: 'DmmMiniportInterfaceReleaseMonitorFrequencyRange', 7027: 'DmmMiniportInterfaceGetNumMonitorDescriptors', 7028: 'DmmMiniportInterfaceAcquireFirstMonitorDescriptor', 7029: 'DmmMiniportInterfaceAcquireNextMonitorDescriptor', 7030: 'DmmMiniportInterfaceReleaseMonitorDescriptor', 7031: 'DmmMiniportInterfaceGetNumPaths', 7032: 'DmmMiniportInterfaceGetNumPathsFromSource', 7033: 'DmmMiniportInterfaceEnumPathTargetsFromSource', 7034: 'DmmMiniportInterfaceGetPathSourceFromTarget', 7035: 'DmmMiniportInterfaceAcquirePath', 7036: 'DmmMiniportInterfaceAcquireFirstPath', 7037: 'DmmMiniportInterfaceAcquireNextPath', 7038: 'DmmMiniportInterfaceUpdatePathSupport', 7039: 'DmmMiniportInterfaceReleasePath', 7040: 'DmmMiniportInterfaceCreateNewPath', 7041: 'DmmMiniportInterfaceAddPath', 7042: 'DmmMiniportInterfaceGetTopology', 7043: 'DmmMiniportInterfaceAcquireSourceModeSet', 7044: 'DmmMiniportInterfaceReleaseSourceModeSet', 7045: 'DmmMiniportInterfaceCreateNewSourceModeSet', 7046: 'DmmMiniportInterfaceAssignSourceModeSet', 7047: 'DmmMiniportInterfaceAssignMultisamplingSet', 5000: 'DdiQueryAdapterInfo', 5001: 'DdiCreateDevice', 5002: 'DdiCreateAllocation', 5003: 'DdiDescribeAllocation', 5004: 'DdiGetStandardAllocationDriverData', 5005: 'DdiDestroyAllocation', 5006: 'DdiAcquireSwizzlingRange', 5007: 'DdiReleaseSwizzlingRange', 5008: 'DdiPatch', 5009: 'DdiCommitVidPn', 5010: 'DdiSetVidPnSourceAddress', 5011: 'DdiSetVidPnSourceVisibility', 5012: 'DdiUpdateActiveVidPnPresentPath', 5013: 'DdiSubmitCommand', 5014: 'DdiPreemptCommand', 5015: 'DdiQueryCurrentFence', 5016: 'DdiBuildPagingBuffer', 5017: 'DdiSetPalette', 5018: 'DdiSetPointerShape', 5019: 'DdiSetPointerPosition', 5020: 'DdiResetFromTimeout', 5021: 'DdiRestartFromTimeout', 5022: 'DdiEscape', 5023: 'DdiCollectDbgInfo', 5024: 'DdiRecommendFunctionalVidPn', 5025: 'DdiIsSupportedVidPn', 5026: 'DdiEnumVidPnCofuncModality', 5027: 'DdiDestroyDevice', 5028: 'DdiOpenAllocation', 5029: 'DdiCloseAllocation', 5030: 'DdiRender', 5031: 'DdiPresent', 5032: 'DdiCreateOverlay', 5033: 'DdiUpdateOverlay', 5034: 'DdiFlipOverlay', 5035: 'DdiDestroyOverlay', 5036: 'DdiGetScanLine', 5037: 'DdiRecommendMonitorModes', 5038: 'DdiControlInterrupt', 5039: 'DdiStopCapture', 5040: 'DdiRecommendVidPnTopology', 5041: 'DdiCreateContext', 5042: 'DdiDestroyContext', 5043: 'DdiNotifyDpc', 5044: 'DdiSetDisplayPrivateDriverFormat', 5045: 'DdiRenderKm', 5046: 'DdiAddTargetMode', 5047: 'DdiQueryVidPnHWCapability', 5048: 'DdiPresentDisplayOnly', 5049: 'DdiQueryDependentEngineGroup', 5050: 'DdiQueryEngineStatus', 5051: 'DdiResetEngine', 5052: 'DdiCancelCommand', 5053: 'DdiGetNodeMetadata', 5054: 'DdiControlInterrupt2', 5055: 'DdiCheckMultiPlaneOverlaySupport', 3008: 'DxgkCddPresent', 3009: 'DxgkCddSetGammaRamp', 5058: 'DdiGetRootPageTableSize', 5059: 'DdiSetRootPageTable', 3012: 'DxgkCddSetPointerShape', 5061: 'DdiMapCpuHostAperture', 5062: 'DdiUnmapCpuHostAperture', 5063: 'DdiSubmitCommandVirtual', 5064: 'DdiCreateProcess', 5065: 'DdiDestroyProcess', 5066: 'DdiRenderGdi', 5067: 'DdiCheckMultiPlaneOverlaySupport2', 5068: 'DdiSetStablePowerState', 5069: 'DdiSetVideoProtectedRegion', 3022: 'DxgkCddDrvColorFill', 3023: 'DxgkCddDrvStrokePath', 3024: 'DxgkCddDrvAlphaBlend', 3025: 'DxgkCddDrvLineTo', 3026: 'DxgkCddDrvFillPath', 3027: 'DxgkCddDrvStrokeAndFillPath', 3028: 'DxgkCddDrvStretchBltROP', 3029: 'DxgkCddDrvPlgBlt', 3030: 'DxgkCddDrvStretchBlt', 3031: 'DxgkCddDrvTextOut', 3032: 'DxgkCddDrvGradientFill', 3033: 'DxgkCddDrvTransparentBlt', 3034: 'DxgkCddOpenResource', 3035: 'DxgkCddQueryResourceInfo', 3036: 'DxgkCddSubmitPresentHistory', 3037: 'DxgkCddCreateDeviceBitmap', 3038: 'DxgkCddUpdateGdiMem', 3039: 'DxgkCddAddCommand', 3040: 'DxgkCddEnableLite', 3041: 'DxgkCddAssertModeInternal', 3042: 'DxgkCddSetLiteModeChange', 3043: 'DxgkCddPresentDisplayOnly', 3044: 'DxgkCddSignalGdiContext', 3045: 'DxgkCddWaitGdiContext', 3046: 'DxgkCddSignalDxContext', 3047: 'DxgkCddWaitDxContext', 3048: 'DxgkCddStartDxInterop', 3049: 'DxgkCddEndDxInterop', 3050: 'DxgkCddAddD3DDirtyRect', 3051: 'DxgkCddDxGdiInteropFailed', 3052: 'DxgkCddSyncDxAccess', 3053: 'DxgkCddFlushCpuCache', 3054: 'DxgkCddLockMdlPages', 3055: 'DxgkCddOpenResourceFromNtHandle', 3056: 'DxgkCddQueryResourceInfoFromNtHandle', 3057: 'DxgkCddUnlockMdlPages', 3058: 'DxgkCddTrimStagingSize', 7059: 'DmmMiniportInterfaceGetAdditionalMonitorModesSet', 13150: 'MiracastUmdDriverCbReportSessionStatus', 13151: 'MiracastUmdDriverCbMiracastIoControl', 13152: 'MiracastUmdDriverCbReportStatistic', 13153: 'MiracastUmdDriverCbGetNextChunkData', 13154: 'MiracastUmdDriverCbRegisterForDataRateNotifications', 1004: 'DpiDispatchIoctl', 7048: 'DmmMiniportInterfaceAcquireTargetModeSet', 7049: 'DmmMiniportInterfaceReleaseTargetModeSet', 7050: 'DmmMiniportInterfaceCreateNewTargetModeSet', 7051: 'DmmMiniportInterfaceAssignTargetModeSet', 7052: 'DmmMiniportInterfaceAcquireMonitorSourceModeSet', 7053: 'DmmMiniportInterfaceReleaseMonitorSourceModeSet', 1000: 'DpiAddDevice', 7055: 'DmmMiniportInterfaceGetMonitorDescriptorSet', 7056: 'DmmMiniportInterfaceQueryVidPnInterface', 7057: 'DmmMiniportInterfaceQueryMonitorInterface', 7058: 'DmmMiniportInterfaceRemovePath', 1001: 'DpiDispatchClose', 7060: 'DmmMiniportInterfaceReleaseAdditionalMonitorModesSet', 1002: 'DpiDispatchCreate', 1003: 'DpiDispatchInternalIoctl', 4000: 'DpiDxgkDdiAddDevice', 4001: 'DpiDxgkDdiStartDevice', 4002: 'DpiDxgkDdiStopDevice', 4003: 'DpiDxgkDdiRemoveDevice', 6052: 'DmmInterfaceCreateVidPn', 6053: 'DmmInterfaceCreateVidPnFromActive', 6054: 'DmmInterfaceCreateVidPnCopy', 1005: 'DpiDispatchPnp', 6056: 'DmmInterfaceIsUsingDefaultMonitorProfile', 6057: 'DmmInterfaceIsMonitorConnected', 6058: 'DmmInterfaceRemoveCopyProtection', 6059: 'DmmInterfaceGetPathImportance', 1006: 'DpiDispatchPower', 6061: 'DmmInterfaceEnumPaths', 1007: 'DpiDispatchSystemControl', 1008: 'DpiDriverUnload', 3000: 'DxgkCddCreate', 6055: 'DmmInterfaceReleaseVidPn', 3001: 'DxgkCddDestroy', 3002: 'DxgkCddEnable', 3003: 'DxgkCddDisable', 3004: 'DxgkCddGetDisplayModeList', 3005: 'DxgkCddGetDriverCaps', 3006: 'DxgkCddLock', 3007: 'DxgkCddUnlock', 3010: 'DxgkCddSetPalette', 3011: 'DxgkCddSetPointerPosition', 3013: 'DxgkCddTerminateThread', 3014: 'DxgkCddSetOrigin', 3015: 'DxgkCddWaitForVerticalBlankEvent', 14000: 'VidMmProcessOperations', 3016: 'DxgkCddSyncGPUAccess', 3017: 'DxgkCddCreateAllocation', 3018: 'DxgkCddDestroyAllocation', 3019: 'DxgkCddBltToPrimary', 3020: 'DxgkCddGdiCommand', 3021: 'DxgkCddDrvBitBlt', 12000: 'BLTQUEUE_Present', 6060: 'DmmInterfaceGetNumPaths', 8000: 'ProbeAndLockPages', 8001: 'UnlockPages', 8002: 'MapViewOfAllocation', 8003: 'UnmapViewOfAllocation', 8004: 'ProcessHeapAllocate', 8005: 'ProcessHeapRotate', 8006: 'BootInt10ModeChange', 8007: 'ResumeInt10ModeChange', 8008: 'FlushAllocationCache', 8009: 'NotifyVSync', 8010: 'MakeProcessIdleToFlushTlb', 6000: 'DmmInterfaceAcquiredPreferredMonitorSourceMode', 6001: 'DmmInterfaceReleaseMonitorSourceMode', 6002: 'DmmInterfaceGetNumSourceModes', 6003: 'DmmInterfaceAcquireFirstSourceMode', 6004: 'DmmInterfaceAcquireNextSourceMode', 6005: 'DmmInterfaceAcquirePinnedSourceMode', 6006: 'DmmInterfaceReleaseSourceMode', 6007: 'DmmInterfacePinSourceMode', 6008: 'DmmInterfaceUnpinSourceMode', 6009: 'DmmInterfaceGetNumTargetModes', 6010: 'DmmInterfaceAcquireFirstTargetMode', 6011: 'DmmInterfaceAcquireNextTargetMode', 6012: 'DmmInterfaceAcquriePinnedTargetMode', 6013: 'DmmInterfaceReleaseTargetMode', 6014: 'DmmInterfaceCompareTargetMode', 6015: 'DmmInterfacePinTargetMode', 6016: 'DmmInterfaceUnpinTargetMode', 6017: 'DmmInterfaceIsTargetModeSupportedByMonitor', 6018: 'DmmInterfaceGetNumPathsFromSource', 6019: 'DmmInterfaceEnumPathTargetsFromSource', 6020: 'DmmInterfaceGetPathSourceFromTarget', 6021: 'DmmInterfaceAcquirePath', 6022: 'DmmInterfaceReleasePath', 6023: 'DmmInterfaceAddPath', 6024: 'DmmInterfaceRemovePath', 6025: 'DmmInterfaceRemoveAllPaths', 6026: 'DmmInterfacePinScaling', 6027: 'DmmInterfaceUnpinScaling', 6028: 'DmmInterfacePinRotation', 6029: 'DmmInterfaceUnpinRotation', 6030: 'DmmInterfaceRecommendVidPnTopology', 6031: 'DmmInterfaceFindFirstAvailableTarget', 6032: 'DmmInterfaceRestoreFromLkgForSource', 6033: 'DmmInterfaceGetTopology', 6034: 'DmmInterfaceAcquireSourceModeSet', 6035: 'DmmInterfaceReleaseSourceModeSet', 6036: 'DmmInterfaceAcquireTargetModeSet', 6037: 'DmmInterfaceReleaseTargetModeSet', 6038: 'DmmInterfaceAcquireMonitorSourceModeSet', 6039: 'DmmInterfaceReleaseMonitorSourceModeSet', 6040: 'DmmInterfaceGetNumSources', 6041: 'DmmInterfaceAcquireFirstSource', 6042: 'DmmInterfaceAcquireNextSource', 6043: 'DmmInterfaceReleaseSource', 6044: 'DmmInterfaceGetNumTargets', 6045: 'DmmInterfaceAcquireFirstTarget', 6046: 'DmmInterfaceAcquireNextTarget', 6047: 'DmmInterfaceReleaseTarget', 6048: 'DmmInterfaceAcquireSourceSet', 6049: 'DmmInterfaceReleaseSourceSet', 6050: 'DmmInterfaceAcquireTargetSet', 6051: 'DmmInterfaceReleaseTargetSet', 4004: 'DpiDxgkDdiDispatchIoRequest', 4005: 'DpiDxgkDdiQueryChildRelations', 4006: 'DpiDxgkDdiQueryChildStatus', 4007: 'DpiDxgkDdiQueryDeviceDescriptor', 4008: 'DpiDxgkDdiSetPowerState', 4009: 'DpiDxgkDdiNotifyAcpiEvent', 4010: 'DpiDxgkDdiUnload', 4011: 'DpiDxgkDdiControlEtwLogging', 4012: 'DpiDxgkDdiQueryInterface', 4013: 'DpiDpcForIsr', 4014: 'DpiFdoMessageInterruptRoutine', 4015: 'VidSchDdiNotifyInterrupt', 4016: 'VidSchiCallNotifyInterruptAtISR', 4017: 'DpiDxgkDdiStopDeviceAndReleasePostDisplayOwnership', 4018: 'DpiDxgkDdiGetChildContainerId', 4019: 'DpiDxgkDdiNotifySurpriseRemoval', 4020: 'DpiFdoThermalActiveCooling', 4021: 'DpiFdoThermalPassiveCooling', 4022: 'DxgkCbIndicateChildStatus', 2000: 'DxgkProcessCallout', 2001: 'DxgkOpenAdapter', 2002: 'DxgkCloseAdapter', 2003: 'DxgkCreateAllocation', 2004: 'DxgkQueryResourceInfo', 2005: 'DxgkOpenResource', 2006: 'DxgkDestroyAllocation', 2007: 'DxgkSetAllocationPriority', 2008: 'DxgkQueryAllocationResidency', 2009: 'DxgkCreateDevice', 2010: 'DxgkDestroyDevice', 2011: 'DxgkLock', 2012: 'DxgkUnlock', 2013: 'DxgkRender', 2014: 'DxgkGetRuntimeData', 2015: 'DxgkQueryAdapterInfo', 2016: 'DxgkEscape', 2017: 'DxgkGetDisplayModeList', 2018: 'DxgkSetDisplayMode', 2019: 'DxgkGetMultisampleMethodList', 2020: 'DxgkPresent', 2021: 'DxgkGetSharedPrimaryHandle', 2022: 'DxgkCreateOverlay', 2023: 'DxgkUpdateOverlay', 2024: 'DxgkFlipOverlay', 2025: 'DxgkDestroyOverlay', 2026: 'DxgkWaitForVerticalBlankEvent', 2027: 'DxgkSetVidPnSourceOwner', 2028: 'DxgkGetDeviceState', 2029: 'DxgkSetContextSchedulingPriority', 2030: 'DxgkGetContextSchedulingPriority', 2031: 'DxgkSetProcessSchedulingPriorityClass', 2032: 'DxgkGetProcessSchedulingPriorityClass', 2033: 'DxgkReleaseProcessVidPnSourceOwners', 2034: 'DxgkGetScanLine', 2035: 'DxgkSetQueuedLimit', 2036: 'DxgkPollDisplayChildren', 2037: 'DxgkInvalidateActiveVidPn', 2038: 'DxgkCheckOcclusion', 2039: 'DxgkCreateContext', 2040: 'DxgkDestroyContext', 2041: 'DxgkCreateSynchronizationObject', 2042: 'DxgkDestroySynchronizationObject', 2043: 'DxgkWaitForSynchronizationObject', 2044: 'DxgkSignalSynchronizationObject', 2045: 'DxgkWaitForIdle', 2046: 'DxgkCheckMonitorPowerState', 2047: 'DxgkCheckExclusiveOwnership'}
PAGING_QUEUE_TYPE = ['UMD', 'DEFAULT', 'EVICT', 'RECLAIM']
VIDMM_OPERATION = {0: 'None', 200: 'CloseAllocation', 202: 'ComplexLock', 203: 'PinAllocation', 204: 'FlushPendingGpuAccess', 205: 'UnpinAllocation', 206: 'MakeResident', 207: 'Evict', 208: 'LockInAperture', 209: 'InitContextAllocation', 210: 'ReclaimAllocation', 211: 'DiscardAllocation', 212: 'SetAllocationPriority', 1000: 'EvictSystemMemoryOfferList', 101: 'RestoreSegments', 102: 'PurgeSegments', 103: 'CleanupPrimary', 104: 'AllocatePagingBufferResources', 105: 'FreePagingBufferResources', 106: 'ReportVidMmState', 107: 'RunApertureCoherencyTest', 108: 'RunUnmapToDummyPageTest', 109: 'DeferredCommand', 110: 'SuspendMemorySegmentAccess', 111: 'ResumeMemorySegmentAccess', 112: 'EvictAndFlush', 113: 'CommitVirtualAddressRange', 114: 'UncommitVirtualAddressRange', 115: 'DestroyVirtualAddressAllocator', 116: 'PageInDevice', 117: 'MapContextAllocation', 118: 'InitPagingProcessVaSpace'}
SYNC_REASON = ['CREATE', 'DESTROY', 'OPEN', 'CLOSE', 'REPORT']
OPCODES = ['Info', 'Start', 'Stop', 'DCStart', 'DCEnd', 'Extension']


class ETWXMLHandler:
    def __init__(self, args, callbacks):
        self.args = args
        self.callbacks = callbacks
        self.count = 0
        self.process_names = {}
        self.thread_pids = {}
        self.ftrace = open(args.input + '.ftrace', 'w') if "gt" in args.format else None
        self.first_ftrace_record = True
        self.gui_packets = {}
        self.files = {}
        self.irps = {}
        self.context_to_node = {}

    def convert_time(self, time):
        return 1000000000 * (int(time, 16) if '0x' in str(time) else int(time)) / self.PerfFreq

    def MapReasonToState(self, state, wait_reason):
        if wait_reason in [5, 12]:  # Suspended, WrSuspended
            return 'D'  # uninterruptible sleep (usually IO)
        elif wait_reason in [35, 34, 32, 23, 11, 4, 28]: # WrGuardedMutex, WrFastMutex, WrPreempted, WrProcessInSwap, WrDelayExecution, DelayExecution, WrPushLock
            return 'S'  # interruptible sleep (waiting for an event to complete)
        elif wait_reason in [22, 36]:  # WrRundown, WrTerminated
            return 'X'  # dead (should never be seen)
        elif wait_reason in [1, 2, 8, 9]:  # WrFreePage, WrPageIn, FreePage, PageIn
            return 'W'  # paging
        else:
            if state == 3:  # Standby
                return 'D'  # uninterruptible sleep
            elif state == 4:  # Terminated
                return 'X'  # dead
            elif state == 5:  # Waiting
                return 'S'  # interruptible sleep (waiting for an event to complete)
            return 'R'
        """
        States:
        0	Initialized
        1	Ready
        2	Running
        3	Standby
        4	Terminated
        5	Waiting
        6	Transition
        7	DeferredReady

        Windows: https://msdn.microsoft.com/en-us/library/windows/desktop/aa964744(v=vs.85).aspx
        0	Executive           13	WrUserRequest       26	WrKernel
        1	FreePage            14	WrEventPair         27	WrResource
        2	PageIn              15	WrQueue             28	WrPushLock
        3	PoolAllocation      16	WrLpcReceive        29	WrMutex
        4	DelayExecution      17	WrLpcReply          30	WrQuantumEnd
        5	Suspended           18	WrVirtualMemory     31	WrDispatchInt
        6	UserRequest         19	WrPageOut           32	WrPreempted
        7	WrExecutive         20	WrRendezvous        33	WrYieldExecution
        8	WrFreePage          21	WrKeyedEvent        34	WrFastMutex
        9	WrPageIn            22	WrTerminated        35	WrGuardedMutex
        10	WrPoolAllocation    23	WrProcessInSwap     36	WrRundown
        11	WrDelayExecution    24	WrCpuRateControl
        12	WrSuspended         25	WrCalloutStack

        Linux:
        D    uninterruptible sleep (usually IO)
        R    running or runnable (on run queue)
        S    interruptible sleep (waiting for an event to complete)
        T    stopped, either by a job control signal or because it is being traced.
        W    paging (not valid since the 2.6.xx kernel)
        X    dead (should never be seen)
        Z    defunct ("zombie") process, terminated but not reaped by its parent.

        From google trace parser:
        'S' SLEEPING
        'R' || 'R+' RUNNABLE
        'D' UNINTR_SLEEP
        'T' STOPPED
        't' DEBUG
        'Z' ZOMBIE
        'X' EXIT_DEAD
        'x' TASK_DEAD
        'K' WAKE_KILL
        'W' WAKING
        'D|K' UNINTR_SLEEP_WAKE_KILL
        'D|W' UNINTR_SLEEP_WAKING
        """

    def get_process_name_by_tid(self, tid):
        if self.thread_pids.has_key(tid):
            pid = self.thread_pids[tid]
            if self.process_names.has_key(pid):
                name = self.process_names[pid]['name']
            else:
                name = "PID:%d" % int(pid, 16)
        else:
            name = "TID:%d" % tid
        return name

    def handle_file_name(self, file):
        file_name = file.encode('utf-8').replace('\\', '/').replace('"', r'\"')
        file_name = file_name.split('/')
        file_name.reverse()
        return file_name[0] + " " + "/".join(file_name[1:])

    def MSNT_SystemTrace(self, system, data, info):
        if info['EventName'] == 'EventTrace':
            if info['Opcode'] == 'Header':
                self.PerfFreq = int(data['PerfFreq'])
                for callback in self.callbacks.callbacks:
                    callback("metadata_add", {'domain':'GPU', 'str':'__process__', 'pid':-1, 'tid':-1, 'data':'GPU Engines', 'time': self.convert_time(system['time']), 'delta': -2})
        elif info['EventName'] == 'DiskIo':
            if info['Opcode'] in ['FileDelete', 'FileRundown']:
                if self.files.has_key(data['FileObject']):
                    file = self.files[data['FileObject']]
                    if file.has_key('pid'):
                        call_data = {'tid': file['tid'], 'pid': file['pid'], 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file['name'], 'type':11, 'id': int(data['FileObject'], 16)}
                        self.callbacks.on_event("object_delete", call_data)
                    del self.files[data['FileObject']]
            elif info['Opcode'] in ['Read', 'Write', 'HardFault', 'FlushBuffers', 'WriteInit', 'ReadInit', 'FlushInit']:
                tid = int(data['IssuingThreadId']) if data.has_key('IssuingThreadId') else int(data['TThreadId'], 16) if data.has_key('TThreadId') else None
                if tid == None:
                    return
                if not data.has_key('FileObject'):
                    if self.irps.has_key(data['Irp']):
                        data['FileObject'] = self.irps[data['Irp']]
                    else:
                        return
                if self.files.has_key(data['FileObject']) and self.thread_pids.has_key(tid):
                    file = self.files[data['FileObject']]
                    pid = int(self.thread_pids[tid], 16)
                    call_data = {'tid': tid, 'pid': pid, 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file['name'], 'type':10, 'id': int(data['FileObject'], 16)}
                    file['tid'] = tid
                    file['pid'] = pid
                    if file['creation'] != None:  # write creation on first operation where tid is known
                        creation = call_data.copy()
                        creation['type'] = 9
                        creation['time'] = file['creation']
                        self.callbacks.on_event("object_new", creation)
                        file['creation'] = None
                    if data.has_key('Irp'):
                        self.irps[data['Irp']] = data['FileObject']
                    data['OPERATION'] = info['Opcode']
                    call_data['args'] = {'snapshot': data}
                    self.callbacks.on_event("object_snapshot", call_data)
            else:
                print info['Opcode']
        elif info['EventName'] == 'FileIo':
            if info['Opcode'] == 'FileCreate':
                file_name = self.handle_file_name(data['FileName'])
                if '.sea/' not in file_name:  # ignore own files - they are toooo many in the view
                    self.files[data['FileObject']] = {'name': file_name, 'creation': self.convert_time(system['time'])}
            elif info['Opcode'] == 'Create':
                file_name = self.handle_file_name(data['OpenPath'])
                if '.sea/' not in file_name:  # ignore own files - they are toooo many in the view
                    self.files[data['FileObject']] = {'name': file_name, 'creation': None}
                    call_data = {'tid': int(system['tid']), 'pid': int(system['pid']), 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file_name, 'type':9, 'id': int(data['FileObject'], 16)}
                    self.callbacks.on_event("object_new", call_data)
            elif info['Opcode'] in ['Close', 'FileDelete', 'Delete']:
                if self.files.has_key(data['FileObject']):
                    file = self.files[data['FileObject']]
                    call_data = {'tid': int(system['tid']), 'pid': int(system['pid']), 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file['name'], 'type':11, 'id': int(data['FileObject'], 16)}
                    self.callbacks.on_event("object_delete", call_data)
                    del self.files[data['FileObject']]
            elif info['Opcode'] not in ['OperationEnd', 'Cleanup', 'QueryInfo']:
                if self.files.has_key(data['FileObject']):
                    file = self.files[data['FileObject']]
                    tid = int(system['tid'])
                    pid = int(system['pid'])
                    call_data = {'tid': tid, 'pid': pid, 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file['name'], 'type':10, 'id': int(data['FileObject'], 16)}
                    file['tid'] = tid
                    file['last_access'] = call_data['time']
                    file['pid'] = pid
                    if data.has_key('IrpPtr'):
                        self.irps[data['IrpPtr']] = data['FileObject']
                    data['OPERATION'] = info['Opcode']
                    call_data['args'] = {'snapshot': data}
                    self.callbacks.on_event("object_snapshot", call_data)
        else:
            if 'Start' in info['Opcode']:
                event = info['EventName']
                if event in ['Process', 'Defunct']:
                    self.process_names[data['ProcessId']] = {'name': data['ImageFileName'].split('.')[0], 'cmd': data['CommandLine']}
                elif event == 'Thread':
                    pid = data['ProcessId'] if '0x0' != data['ProcessId'] else hex(int(system['pid']))
                    self.thread_pids[int(data['TThreadId'], 16)] = pid
            elif info['Opcode'] == 'CSwitch':
                if self.ftrace == None and not self.first_ftrace_record:
                    return
                time = self.convert_time(system['time'])
                if not self.callbacks.check_time_in_limits(time):
                    return
                # mandatory: prevState, nextComm, nextPid, nextPrio
                prev_tid = int(data['OldThreadId'], 16)
                prev_name = self.get_process_name_by_tid(prev_tid)
                next_tid = int(data['NewThreadId'], 16)

                if self.first_ftrace_record:
                    self.ftrace = open(self.args.input + '.ftrace', 'w') if "gt" in self.args.format else None
                    self.first_ftrace_record = False
                    if not self.ftrace:
                        return
                    self.ftrace.write("# tracer: nop\n")
                    args = (prev_name, prev_tid, int(system['cpu']), time / 1000000000., time / 1000000000.)
                    ftrace = "%s-%d [%03d] .... %.6f: tracing_mark_write: trace_event_clock_sync: parent_ts=%.6f\n" % args
                    self.ftrace.write(ftrace)
                args = (
                    prev_name, prev_tid, int(system['cpu']), time / 1000000000.,
                    prev_name, prev_tid, int(data['OldThreadPriority']), self.MapReasonToState(int(data['OldThreadState']), int(data['OldThreadWaitReason'])),
                    self.get_process_name_by_tid(next_tid), next_tid, int(data['NewThreadPriority'])
                )
                ftrace = "%s-%d [%03d] .... %.6f: sched_switch: prev_comm=%s prev_pid=%d prev_prio=%d prev_state=%s ==> next_comm=%s next_pid=%d next_prio=%d\n" % args
                self.ftrace.write(ftrace)

    def auto_break_gui_packets(self, call_data, tid, begin):
        id = call_data['id']
        if begin:
            self.gui_packets.setdefault(tid, {})[id] = call_data
        else:
            if self.gui_packets.has_key(tid) and self.gui_packets[tid].has_key(id):
                del self.gui_packets[tid][id] #the task has ended, removing it from the pipeline
                for begin_data in self.gui_packets[tid].itervalues(): #finish all and start again to form melting task queue
                    begin_data['time'] = call_data['time'] #new begin for every task is here
                    end_data = begin_data.copy() #the end of previous part of task is also here
                    end_data['type'] = call_data['type']
                    self.callbacks.on_event('task_end_overlapped', end_data) #finish it
                    self.callbacks.on_event('task_begin_overlapped', begin_data)# and start again

    def on_event(self, system, data, info, static={'queue':{}, 'frames':{}, 'paging':{}, 'dmabuff':{}, 'tex2d':{}, 'resident':{}, 'fence':{}}):
        if self.count % ProgressConst == 0:
            self.progress.tick(self.file.tell())
        self.count += 1
        if not info or not data:
            return
        if not isinstance(data, dict):
            return self.on_binary(system, data, info)
        opcode = info['Opcode'] if info.has_key('Opcode') else ""
        if system['provider'] == '{9e814aad-3204-11d2-9a82-006008a86939}':  # MSNT_SystemTrace
            return self.MSNT_SystemTrace(system, data, info)

        call_data = {
            'tid': int(system['tid']), 'pid': int(system['pid']), 'domain': system['provider'],
            'time': self.convert_time(data['SyncQPCTime'] if data.has_key('SyncQPCTime') else system['time']),
            'str': info['Task'] if info.has_key('Task') and info['Task'] else 'Unknown',
            'args': data,
        }

        if call_data['str'] == 'SelectContext':  # Microsoft-Windows-DxgKrnl
            context = data['hContext']
            node = data['NodeOrdinal']
            self.context_to_node[context] = node
            return

        if data.has_key('QuantumStatus'):
            data['QuantumStatusStr'] = QUANTUM_STATUS[int(data['QuantumStatus'])]

        if 'Start' in opcode:
            call_data["type"] = 2
            type = "task_begin_overlapped"
        elif 'Stop' in opcode:
            call_data["type"] = 3
            type = "task_end_overlapped"
        else:
            call_data["type"] = 5
            type = "marker"
            call_data['data'] = 'track'
        relation = None

        if call_data['str'] == 'DmaPacket':  # Microsoft-Windows-DxgKrnl
            context = data['hContext']
            if not self.context_to_node.has_key(context) or 'Info' in opcode:
                return  # no node info at this moment, just skip it. Or may be keep until it is known?
            call_data['pid'] = -1  # GUI 'process'
            tid = int(self.context_to_node[context])
            call_data['tid'] = tid
            call_data['str'] = DMA_PACKET_TYPE[int(data['PacketType'])]
            id = int(data['uliSubmissionId'] if data.has_key('uliSubmissionId') else data['uliCompletionId'])
            call_data['id'] = id
            if 'Start' in opcode:
                if static['queue'].has_key(int(data['ulQueueSubmitSequence'])):
                    relation = (call_data.copy(), static['queue'][int(data['ulQueueSubmitSequence'])], call_data)
                    relation[0]['parent'] = id
                self.auto_break_gui_packets(call_data, 2 ** 64 + tid, True)
            else:
                self.auto_break_gui_packets(call_data, 2 ** 64 + tid, False)

        elif call_data['str'] == 'QueuePacket':  # Microsoft-Windows-DxgKrnl
            if 'Info' in opcode:
                return
            call_data['tid'] = -call_data['tid']
            id = int(data['SubmitSequence'])
            if not data.has_key('PacketType'):  # workaround, PacketType is not set for Waits
                call_data['str'] = 'WAIT'
                assert (data.has_key('FenceValue'))
            else:
                call_data['str'] = QUEUE_PACKET_TYPE[int(data['PacketType'])]
            call_data['id'] = id
            if 'Start' in opcode:
                if static['queue'].has_key(id):  # forcefully closing the previous one
                    closing = call_data.copy()
                    closing['type'] = 3
                    closing['id'] = id
                    self.callbacks.on_event("task_end_overlapped", closing)
                static['queue'][id] = call_data
                self.auto_break_gui_packets(call_data, call_data['tid'], True)
                if data.has_key('FenceValue') and static['fence'].has_key(data['FenceValue']):
                    relation = (call_data.copy(), static['fence'][data['FenceValue']], call_data)
                    relation[0]['parent'] = data['FenceValue']
                    del static['fence'][data['FenceValue']]
            elif 'Stop' in opcode:
                if not static['queue'].has_key(id):
                    return
                call_data['pid'] = static['queue'][id]['pid']
                call_data['tid'] = static['queue'][id]['tid']
                del static['queue'][id]
                self.auto_break_gui_packets(call_data, call_data['tid'], False)

        elif call_data['str'] == 'SCHEDULE_FRAMEINFO':  # Microsoft-Windows-Dwm-Core
            presented = int(data['qpcPresented'], 16)
            if presented:
                begin = int(data['qpcBegin'], 16)
                call_data['time'] = self.convert_time(begin)
                call_data['type'] = 7  # to make it frame
                call_data['pid'] = -1  # to make it GUI
                del call_data['tid']  # to be global for GUI
                end_data = {'time': self.convert_time(int(data['qpcFrame'], 16))}
                self.callbacks.complete_task('frame', call_data, end_data)
            return

        elif 'Profiler' in call_data['str']:  # Microsoft-Windows-DxgKrnl
            func = int(data['Function'])
            name = FUN_NAMES[func] if FUN_NAMES.has_key(func) else 'Unknown'
            call_data['str'] = name
            call_data['id'] = func

        elif call_data['str'] == 'MakeResident':  # Microsoft-Windows-DxgKrnl
            if 'Start' in opcode:
                static['resident'].setdefault(system['tid'], []).append(data)
            elif 'Stop' in opcode:
                resident = static['resident'][system['tid']] if static['resident'].has_key(system['tid']) else []
                if len(resident):
                    saved = resident.pop()
                else:
                    return
                data.update(saved)
                static['fence'][data['PagingFenceValue']] = call_data
            call_data['id'] = int(data['pSyncObject'], 16)

        elif call_data['str'] == 'PagingQueuePacket':  # Microsoft-Windows-DxgKrnl
            if 'Info' in opcode:
                return
            call_data['tid'] = -call_data['tid']
            id = int(data['PagingQueuePacket'], 16)
            call_data['id'] = id
            if data.has_key('PagingQueueType'):
                VidMmOpType = int(data['VidMmOpType'])
                call_data['str'] = PAGING_QUEUE_TYPE[int(data['PagingQueueType'])] + ":" + (VIDMM_OPERATION[VidMmOpType] if VIDMM_OPERATION.has_key(VidMmOpType) else "Unknown")
                static['paging'][id] = call_data
            elif static['paging'].has_key(id):
                start = static['paging'][id]
                call_data['str'] = start['str']
                call_data['pid'] = start['pid']
                call_data['tid'] = start['tid']
                del static['paging'][id]

        elif call_data['str'] == 'PagingPreparation':  # Microsoft-Windows-DxgKrnl
            if 'Info' in opcode: return
            pDmaBuffer = data['pDmaBuffer']
            call_data['id'] = int(pDmaBuffer, 16)
            if 'Stop' in opcode and static['dmabuff'].has_key(pDmaBuffer):
                call_data['args'].update(static['dmabuff'][pDmaBuffer])
                del static['dmabuff'][pDmaBuffer]
        elif call_data['str'] == 'AddDmaBuffer':  # Microsoft-Windows-DxgKrnl
            static['dmabuff'][data['pDmaBuffer']] = data  # parse arguments for PagingPreparation from AddDmaBuffer
            return

        elif call_data['str'] == 'Present':  # Microsoft-Windows-DxgKrnl
            if 'Start' in opcode:
                call_data["type"] = 0
                type = "task_begin"
            elif 'Stop' in opcode:
                call_data["type"] = 1
                type = "task_end"
            else:
                return
            """XXX gives nothing
            elif call_data['str'] == 'Texture2D':
                if not data.has_key('pID3D11Resource'):
                    return
                obj = data['pID3D11Resource']
                if static['tex2d'].has_key(obj):
                    obj = static['tex2d'][obj]
                    if 'Stop' in opcode:
                        del static['tex2d'][data['pID3D11Resource']]
                if info.has_key('Message'):
                    data['OPERATION'] = info['Message']
                else:
                    data['OPERATION'] = 'Texture2D'
                call_data['str'] = obj
                call_data['args'] = {'snapshot': data}
                call_data['id'] = int(data['pID3D11Resource'], 16)
                return self.callbacks.on_event("object_snapshot", call_data)
            elif call_data['str'] == 'Name': #names for Texture2D
                static['tex2d'][data['pObject']] = data['DebugObjectName']
                return
            elif call_data['str'] in ['Fence', 'MonitoredFence', 'SynchronizationMutex', 'ReportSyncObject']:
                if 'Info' in opcode:
                    del call_data['data']
                if data.has_key('pSyncObject'):
                    obj = data['pSyncObject']
                else:
                    obj = data['hSyncObject']
                call_data['id'] = int(obj, 16) #QueuePacket.ObjectArray refers to it
                data['OPERATION'] = call_data['str']
                if data.has_key('Reason'):
                    data['OPERATION'] += ":" + SYNC_REASON[int(data['Reason'])]
                call_data['str'] = "SyncObject:" + obj
                call_data['args'] = {'snapshot': data}
                return self.callbacks.on_event("object_snapshot", call_data)

            elif call_data['str'] == 'ProcessAllocationDetails':
                if 'Info' in opcode: return
                call_data['id'] = int(data['Handle'], 16)
            """
        else:
            return

        self.callbacks.on_event(type, call_data)
        assert (type == TaskTypes[call_data['type']])
        if relation:
            if self.callbacks.check_time_in_limits(relation[0]['time']):
                for callback in self.callbacks.callbacks:
                    callback.relation(*relation)

    def finish(self):
        for id, file in self.files.iteritems():
            if file.has_key('last_access'):  # rest aren't rendered anyways
                call_data = {'tid': file['tid'], 'pid': file['pid'], 'domain': 'MSNT_SystemTrace', 'time': file['last_access'], 'str': file['name'], 'type':11, 'id': int(id, 16)}
                self.callbacks.on_event("object_delete", call_data)

    def on_binary(self, system, data, info):
        opcode = int(system['Opcode'])
        if opcode >= len(OPCODES):
            return
        if info == '{fdf76a97-330d-4993-997e-9b81979cbd40}':  # DX - Create/Dest Context
            """
            struct context_t
            {
                uint64_t device;
                uint32_t nodeOrdinal;
                uint32_t engineAffinity;
                uint32_t dmaBufferSize;
                uint32_t dmaBufferSegmentSet;
                uint32_t dmaBufferPrivateDataSize;
                uint32_t allocationListSize;
                uint32_t patchLocationListSize;
                uint32_t contextType;
                uint64_t context;
            };
            """
            chunk = data.decode('hex')
            (device, nodeOrdinal, engineAffinity, dmaBufferSize, dmaBufferSegmentSet, dmaBufferPrivateDataSize, allocationListSize, patchLocationListSize, contextType, context) = struct.unpack('QLLLLLLLLQ', chunk)
            self.context_to_node[context] = nodeOrdinal
        elif info == '{4746dd2b-20d7-493f-bc1b-240397c85b25}':  # DX - Dma Packet
            """
            struct dma_packet_t
            {
                uint64_t context;
                uint32_t unknown1;
                uint32_t submissionId;
                uint32_t unknown2;
                uint32_t submitSequence;
            };
            """
            chunk = data.decode('hex')
            (context, packetType, submissionId, unknown, submitSequence) = struct.unpack('QLLLL', chunk[:24])
            new_info = {'Task': 'DmaPacket', 'Opcode': OPCODES[opcode]}
            system['provider'] = 'Microsoft-Windows-DxgKrnl'
            return self.on_event(system, {'hContext': context, 'PacketType': packetType, 'uliSubmissionId':submissionId, 'ulQueueSubmitSequence': submitSequence}, new_info)
        elif info == '{295e0d8e-51ec-43b8-9cc6-9f79331d27d6}':  # DX - Queue Packet
            """
            struct queue_packet_t
            {
                uint64_t context;
                uint32_t unknown1;
                uint32_t submitSequence;
            };
            """
            chunk = data.decode('hex')
            (context, packetType, submitSequence) = struct.unpack('QLL', chunk[:16])
            new_info = {'Task': 'QueuePacket', 'Opcode': OPCODES[opcode]}
            system['provider'] = 'Microsoft-Windows-DxgKrnl'
            return self.on_event(system, {'SubmitSequence': submitSequence, 'PacketType': packetType}, new_info)

    def parse(self):
        with open(self.args.input) as file:
            self.file = file
            with Progress(os.path.getsize(self.args.input), 50, "Parsing ETW XML: " + os.path.basename(self.args.input)) as progress:
                self.progress = progress
                etwxml = ETWXML(self.on_event, [
                    'Microsoft-Windows-DXGI',
                    # 'Microsoft-Windows-Direct3D11',
                    # 'Microsoft-Windows-D3D10Level9',
                    # 'Microsoft-Windows-Win32k',
                    'Microsoft-Windows-DxgKrnl',
                    'Microsoft-Windows-Dwm-Core',
                    '{9e814aad-3204-11d2-9a82-006008a86939}',  # MSNT_SystemTrace
                    # 'Microsoft-Windows-Shell-Core'
                    None  # Win7 events
                ])
                unhandled_providers = etwxml.parse(file)
                self.finish()
            print "Unhandled providers:", str(unhandled_providers)
        if self.ftrace != None:
            self.ftrace.close()
            for pid, data in self.process_names.iteritems():
                for callback in self.callbacks.callbacks:
                    proc_name = data['name']
                    if len(data['cmd']) > len(proc_name):
                        proc_name = data['cmd'].replace('\\"', '').replace('"', '')
                    callback("metadata_add", {'domain':'IntelSEAPI', 'str':'__process__', 'pid':int(pid, 16), 'tid':-1, 'data':proc_name})


def transform_etw_xml(args):
    tree = default_tree()
    tree['ring_buffer'] = True
    TaskCombiner.disable_handling_leftovers = True
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        handler = ETWXMLHandler(args, callbacks)
        handler.parse()
    TaskCombiner.disable_handling_leftovers = False
    res = callbacks.get_result()
    if handler.ftrace != None:
        res += [handler.ftrace.name]
    return res

IMPORTER_DESCRIPTORS = [{
    'format': 'xml',
    'available': True,
    'importer': transform_etw_xml
}]