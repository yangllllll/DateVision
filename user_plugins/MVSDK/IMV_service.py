from ctypes import *
import datetime
import numpy as np
import cv2
import gc
import os
import sys


from IMVApi import * 


class CameraError(Exception):
    pass


class DahuaCamera:
    IMV_EBayerDemosaic_demosaicNearestNeighbor = 0
    IMV_EBayerDemosaic_demosaicEdgeDirected = 1
    IMV_EBayerDemosaic_demosaicHighQuality = 2
    GVSP_PIXEL_BAYER_GB8 = 0x108000a

    def __init__(self, sdk_path=None):
        if sdk_path:
            sys.path.append(sdk_path)
        self.cam = None
        self._is_connected = False

    @staticmethod
    def display_device_info(device_info_list):
        print("Idx  Type   Vendor              Model           S/N                 DeviceUserID    IP Address")
        print("------------------------------------------------------------------------------------------------")
        for i in range(0, device_info_list.nDevNum):
            p_device_info = device_info_list.pDevInfo[i]
            str_type = ""
            str_vendor_name = ""
            str_mode_name = ""
            str_serial_number = ""
            str_cameraname = ""
            str_ip_adress = ""
            for char_val in p_device_info.vendorName:
                str_vendor_name += chr(char_val)
            for char_val in p_device_info.modelName:
                str_mode_name += chr(char_val)
            for char_val in p_device_info.serialNumber:
                str_serial_number += chr(char_val)
            for char_val in p_device_info.cameraName:
                str_cameraname += chr(char_val)
            for char_val in p_device_info.DeviceSpecificInfo.gigeDeviceInfo.ipAddress:
                str_ip_adress += chr(char_val)
            if p_device_info.nCameraType == typeGigeCamera:  # type: ignore
                str_type = "Gige"
            elif p_device_info.nCameraType == typeU3vCamera:  # type: ignore
                str_type = "U3V"
            print("[%d]  %s   %s    %s      %s     %s           %s" %
                  (i + 1, str_type, str_vendor_name, str_mode_name, str_serial_number, str_cameraname, str_ip_adress))

    @staticmethod
    def get_device_list():
        device_list = IMV_DeviceList()  # type: ignore
        interface_type = IMV_EInterfaceType.interfaceTypeAll  # type: ignore
        n_ret = MvCamera.IMV_EnumDevices(device_list, interface_type)  # type: ignore
        if IMV_OK != n_ret:  # type: ignore
            raise CameraError(f"Enumeration devices failed! ErrorCode {n_ret}")
        if device_list.nDevNum == 0:
            raise CameraError("find no device!")
        return device_list

    def connect(self, camera_index=0):
        if self._is_connected:
            self.close()

        device_list = self.get_device_list()
        self.display_device_info(device_list)

        if camera_index >= device_list.nDevNum:
            raise CameraError(f"Camera index {camera_index + 1} out of range! Available: {device_list.nDevNum}")

        print(f"Selecting camera (index: {camera_index + 1}).")

        self.cam = MvCamera()  # type: ignore
        n_ret = self.cam.IMV_CreateHandle(IMV_ECreateHandleMode.modeByIndex, byref(c_void_p(camera_index)))  # type: ignore
        if IMV_OK != n_ret:  # type: ignore
            raise CameraError(f"Create devHandle failed! ErrorCode {n_ret}")

        n_ret = self.cam.IMV_Open()
        if IMV_OK != n_ret:  # type: ignore
            raise CameraError(f"Open devHandle failed! ErrorCode {n_ret}")

        n_ret = self.cam.IMV_SetEnumFeatureSymbol("TriggerSource", "Software")
        if IMV_OK != n_ret:  # type: ignore
            raise CameraError(f"Set triggerSource value failed! ErrorCode[{n_ret}]")

        n_ret = self.cam.IMV_SetEnumFeatureSymbol("TriggerSelector", "FrameStart")
        if IMV_OK != n_ret:  # type: ignore
            raise CameraError(f"Set triggerSelector value failed! ErrorCode[{n_ret}]")

        n_ret = self.cam.IMV_SetEnumFeatureSymbol("TriggerMode", "Off")
        if IMV_OK != n_ret:  # type: ignore
            raise CameraError(f"Set triggerMode value failed! ErrorCode[{n_ret}]")

        try:
            n_ret = self.cam.IMV_SetIntFeatureValue("GevSCPSPacketSize", 1448)
            if IMV_OK == n_ret:
                print("设置GigE包大小为1448成功")
            else:
                print(f"设置GigE包大小失败: {n_ret}")
        except Exception as e:
            print(f"跳过GigE包大小设置: {e}")



        try:
            n_ret = self.cam.IMV_SetIntFeatureValue("GevStreamChannelSelector", 0)
            if IMV_OK == n_ret:
                print("设置流通道选择器成功")
            else:
                print(f"设置流通道选择器失败: {n_ret}")
        except Exception as e:
            print(f"跳过流通道选择器设置: {e}")

        n_ret = self.cam.IMV_StartGrabbing()
        if IMV_OK != n_ret:  # type: ignore
            raise CameraError(f"Start grabbing failed! ErrorCode {n_ret}")

        self._is_connected = True
        print("Camera connected successfully.")

    def get_frame(self, timeout=1000):
        if not self._is_connected or self.cam is None:
            raise CameraError("Camera not connected! Call connect() first.")

        frame = IMV_Frame()  # type: ignore
        cv_image = None

        try:
            n_ret = self.cam.IMV_GetFrame(frame, timeout)
            if IMV_OK != n_ret:  # type: ignore
                raise CameraError(f"getFrame fail! Timeout:[{timeout}]ms")

            if frame.frameInfo.pixelFormat == self.GVSP_PIXEL_BAYER_GB8:  # type: ignore
                n_dst_buf_size = frame.frameInfo.width * frame.frameInfo.height
                image_buff = frame.pData
                user_buff = (c_ubyte * n_dst_buf_size)()
                memmove(user_buff, image_buff, n_dst_buf_size)
                gray_byte_array = bytearray(user_buff)
                cv_image = np.array(gray_byte_array).reshape(frame.frameInfo.height, frame.frameInfo.width)
            else:
                n_dst_buf_size = frame.frameInfo.width * frame.frameInfo.height * 3

                st_pixel_convert_param = IMV_PixelConvertParam()  # type: ignore
                st_pixel_convert_param.nWidth = frame.frameInfo.width
                st_pixel_convert_param.nHeight = frame.frameInfo.height
                st_pixel_convert_param.ePixelFormat = frame.frameInfo.pixelFormat
                st_pixel_convert_param.pSrcData = frame.pData
                st_pixel_convert_param.nSrcDataLen = frame.frameInfo.size
                st_pixel_convert_param.nPaddingX = frame.frameInfo.paddingX
                st_pixel_convert_param.nPaddingY = frame.frameInfo.paddingY
                st_pixel_convert_param.eBayerDemosaic = self.IMV_EBayerDemosaic_demosaicEdgeDirected
                st_pixel_convert_param.eDstPixelFormat = IMV_EPixelType.gvspPixelBGR8

                p_dst_buf = (c_ubyte * n_dst_buf_size)()
                st_pixel_convert_param.pDstBuf = p_dst_buf
                st_pixel_convert_param.nDstBufSize = n_dst_buf_size

                n_ret = self.cam.IMV_PixelConvert(st_pixel_convert_param)
                if IMV_OK != n_ret:
                    raise CameraError(f"Pixel conversion failed! ErrorCode[{n_ret}]")

                cv_image = np.ctypeslib.as_array(p_dst_buf).reshape(
                    (frame.frameInfo.height, frame.frameInfo.width, 3)
                )

            return cv_image
        finally:
            if frame and self.cam:
                try:
                    self.cam.IMV_ReleaseFrame(frame)
                except Exception:
                    pass

    def close(self):
        if not self._is_connected or self.cam is None:
            return

        try:
            n_ret = self.cam.IMV_StopGrabbing()
            if IMV_OK != n_ret:  # type: ignore
                print("Stop grabbing failed! ErrorCode", n_ret)

            n_ret = self.cam.IMV_Close()
            if IMV_OK != n_ret:  # type: ignore
                print("Close camera failed! ErrorCode", n_ret)

            if hasattr(self.cam, 'handle') and self.cam.handle:
                n_ret = self.cam.IMV_DestroyHandle()
                if IMV_OK != n_ret:  # type: ignore
                    print("Destroy handle failed! ErrorCode", n_ret)
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            self.cam = None
            self._is_connected = False
            print("Camera closed.")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    try:
        with DahuaCamera() as cam:
            img = cam.get_frame()
            print(f"Frame acquired successfully. Shape: {img.shape}, dtype: {img.dtype}")
            cv2.namedWindow('Camera Preview', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('Camera Preview', 640, 480)
            cv2.imshow('Camera Preview', img)
            cv2.waitKey(5000)
            cv2.destroyAllWindows()
    except CameraError as e:
        print(f"Camera error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")