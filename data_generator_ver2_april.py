import sys
import cv2
from cv_bridge import CvBridge, CvBridgeError
import time
import numpy as np
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.uic import loadUi
import roslib
from math import pi, atan, tan, sin, cos, sqrt
from math import degrees as deg
from math import radians as rad
import rospy
import os
from sensor_msgs.msg import Image
from std_msgs.msg import String
# from robotiq_85_msgs.msg import GripperCmd, GripperStat
# import urx
from mask_rcnn_ros.msg import *
from scipy import ndimage
from singleshot import singleshot
from apriltags2_ros.msg import AprilTagDetectionArray
from MeshPly import MeshPly
from torchvision import datasets, transforms
import PyKDL
from pytless import inout,renderer

class UR5_UI(QDialog):

	def __init__(self):
		super(UR5_UI,self).__init__()
		loadUi('UR_Robot_image_collector.ui',self)

		self.setWindowTitle('UR5_UI')

		self.bridge = CvBridge()
		rospy.set_param('calculation',False) ###

		self.objects = ['aloe', 'apple', 'banana', 'board_eraser','clamp','cube', 'cup','diget','diget_sand','duckie','dumbbell','glue','gotica','orange', 'padlock','screw_driver','small_spam','tomato_soup','vitamin_water']
		num_objects = len(self.objects)

		for i in range(num_objects):
			self.Class_Selector.addItem(self.objects[i])
			self.Object_List.addItem(self.objects[i])


		self.save_path = "/media/irobot/Samsung_T5/YOLO/desk_yolo/light_off"

		self.corners3D_list = []
		self.model_list = []

		for i in range(num_objects):
			meshname  = "/home/irobot/David/3D_pose_estimation/real-time_detection/models/%s.ply"%self.objects[i]
			mesh               = MeshPly(meshname) 
			vertices           = np.c_[np.array(mesh.vertices), np.ones((len(mesh.vertices), 1))].transpose()
			vertices = vertices* 1000.0
			corners3D     = self.get_3D_corners(vertices)
			self.corners3D_list.append(corners3D)

			model = inout.load_ply(meshname)
			model['pts'] = model['pts']*1000.0
			self.model_list.append(model)

		self.internal_calibration = self.get_camera_intrinsic()

		self.capture_trigger = False
		self.cal_working = False
		
		self.rgb_save = []
		self.rotation_save = []
		self.translation_save = []
		self.depth_save = []
		self.inspection_save = []
		self.proj_2d_gt_save = []
		self.save_count = 7010 ## JS JS JS
		self.tmp_idx = 0

		self.guide_xcen = 320
		self.guide_ycen = 240
		self.guide_width = 50
		self.guide_height = 50


		self.ppx = 314.00128173828125
		self.ppy = 242.40391540527344
		self.fu = 614.14501953125
		self.fv = 614.680419921875

		self.z_cam_to_tool = 0.520


		self.progressing = False

		self.image_size = [640, 480]
		self.trans_x = [0] * num_objects
		self.trans_y = [0] * num_objects
		self.trans_z = [0] * num_objects

		self.orien_r = [0] * num_objects
		self.orien_p = [0] * num_objects
		self.orien_y = [0] * num_objects

		self.orien_r_btn = [0] * num_objects
		self.orien_p_btn = [0] * num_objects
		self.orien_y_btn = [0] * num_objects

		zero_trans = np.zeros((3,1))
		zero_rotations = np.zeros((3,3))
		zero_proj_2d = np.zeros((8,2))

		self.translation_matrix_list = [zero_trans] * num_objects
		self.rotation_matrix_list = [zero_rotations] * num_objects
		self.proj_2d_gt_list = [zero_proj_2d] * num_objects

		# self.group


		rospy.Subscriber("/camera/color/image_raw", Image, self.callback_rgb)
		rospy.Subscriber("/tag_detections", AprilTagDetectionArray, self.callback_april)
		# rospy.Subscriber("/camera/aligned_depth_to_color/image_raw", Image, self.callback_depth)

		# self.result = Result()
		self.frame = None
		self.frame_result = None

		self.handling_item = None
		self.selected_item = None
		self.activated_items = []
		self.color_items = []


		############ Button Connection ############
		self.Streaming_Start_Btn.clicked.connect(self.start)
		self.Pose1_Btn.clicked.connect(self.pose1)
		self.Home_Btn.clicked.connect(self.home)
		self.Grasp_Btn.clicked.connect(self.grasp)
		self.Save_Count_Btn.clicked.connect(self.save_count_setup)

		self.Orien_roll_down.clicked.connect(lambda:self.change_button('roll_down'))
		self.Orien_roll_up.clicked.connect(lambda:self.change_button('roll_up'))
		self.Orien_pitch_down.clicked.connect(lambda:self.change_button('pitch_down'))
		self.Orien_pitch_up.clicked.connect(lambda:self.change_button('pitch_up'))
		self.Orien_yaw_down.clicked.connect(lambda:self.change_button('yaw_down'))
		self.Orien_yaw_up.clicked.connect(lambda:self.change_button('yaw_up'))
		###########################################

		self.Slider_X.valueChanged.connect(self.change_XYZ)
		self.Slider_Y.valueChanged.connect(self.change_XYZ)
		self.Slider_Z.valueChanged.connect(self.change_XYZ)

		###########################################

		self.Slider_Roll.valueChanged.connect(self.change_RPY)
		self.Slider_Pitch.valueChanged.connect(self.change_RPY)
		self.Slider_Yaw.valueChanged.connect(self.change_RPY)

		self.roi_x_value = self.ROI_X
		self.roi_x = 0
		self.roi_x_value.valueChanged.connect(self.ROI_x_change)
		self.roi_y_value = self.ROI_Y
		self.roi_y = 0
		self.roi_y_value.valueChanged.connect(self.ROI_y_change)
		self.roi_width_value = self.ROI_Width
		self.roi_width = 0
		self.roi_width_value.valueChanged.connect(self.ROI_width_change)
		self.roi_height_value = self.ROI_Height
		self.roi_height = 0
		self.roi_height_value.valueChanged.connect(self.ROI_height_change)

		###########################################


		self.Object_List.itemClicked.connect(self.Select_item_objlist)
		self.Object_List_Activated.itemClicked.connect(self.Select_item_actlist)
		self.Activate.clicked.connect(self.Activate_item)
		self.Deactivate.clicked.connect(self.Deactivate_item)

		self.Class_Selector.currentIndexChanged.connect(self.select_class)


		self.marker_trans = []
		self.marker_trans.append((0, 0.170, 0))
		self.marker_trans.append((0, 0.170, 0))
		self.marker_trans.append((0, 0.170, 0))
		self.marker_trans.append((0, 0.170, 0))
		self.marker_trans.append((0, 0.170, 0))
		self.marker_trans.append((0, 0.170, 0))
		self.marker_trans.append((0, 0.170, 0))
		self.marker_trans.append((0, 0.170, 0))
		# self.marker_trans.append((0, 0, 0))
		# self.marker_trans.append((0, 0, 0))
		# self.marker_trans.append((0, 0, 0))
		# self.marker_trans.append((0, 0, 0))
		# self.marker_trans.append((0, 0, 0))
		# self.marker_trans.append((0, 0, 0))
		# self.marker_trans.append((0, 0, 0))
		# self.marker_trans.append((0, 0, 0))

		self.marker_rot = []
		self.marker_rot.append((0, 0, 0))
		self.marker_rot.append((0, 0, (pi/4)))
		self.marker_rot.append((0, 0, (pi/4)*2))
		self.marker_rot.append((0, 0, (pi/4)*3))
		self.marker_rot.append((0, 0, (pi/4)*4))
		self.marker_rot.append((0, 0, (pi/4)*5))
		self.marker_rot.append((0, 0, (pi/4)*6))
		self.marker_rot.append((0, 0, (pi/4)*7))




		self.marker_list = []
		self.marker_list.append((0,1,2))
		self.marker_list.append((1,2,3))
		self.marker_list.append((2,3,4))
		self.marker_list.append((3,4,5))
		self.marker_list.append((4,5,6))
		self.marker_list.append((5,6,7))
		self.marker_list.append((6,7,8))
		self.marker_list.append((7,8,9))
		self.marker_list.append((8,9,10))
		self.marker_list.append((9,10,11))
		self.marker_list.append((10,11,1))
		self.marker_list.append((11,12,13))
		self.marker_list.append((12,13,14))
		self.marker_list.append((13,14,15))
		self.marker_list.append((14,15,0))
		self.marker_list.append((15,0,1))


	def home(self):
		self.tmp_idx += 1
		print("home")
		# self.tra = self.X + 10

	def save_count_setup(self):
		self.save_count = int(self.Save_Count.text())

	def select_class(self):
		self.handling_item = self.objects.index(self.Class_Selector.currentText())

	def Select_item_objlist(self, item):
		self.selected_item_objlist = item.text()

	def Select_item_actlist(self, item):
		self.selected_item_actlist = item.text()

	def Activate_item(self):
		try:
			self.Object_List_Activated.addItem(self.selected_item_objlist)
			self.activated_items.append(self.selected_item_objlist)
			self.color_items.append(list(np.random.choice(range(256), size=3)))
		except:
			self.Status.setText("object is not selected.")

	def Deactivate_item(self):
		index = self.activated_items.index(self.selected_item_actlist)
		self.Object_List_Activated.takeItem(index)
		del self.activated_items[index]
		del self.color_items[index]

	def change_XYZ(self):
		if self.handling_item != None:
			self.trans_x[self.handling_item] = self.Slider_X.value() / 10.0
			self.trans_y[self.handling_item] = self.Slider_Y.value() / 10.0
			self.trans_z[self.handling_item] = self.Slider_Z.value() / 10.0

			self.Status_x.setText("%i"%self.Slider_X.value())
			self.Status_y.setText("%i"%self.Slider_Y.value())
			self.Status_z.setText("%i"%self.Slider_Z.value())

	def change_RPY(self):
		if self.handling_item != None:
			self.orien_r[self.handling_item] = self.orien_r_btn[self.handling_item] + self.Slider_Roll.value() / 100.0
			self.orien_p[self.handling_item] = self.orien_p_btn[self.handling_item] + self.Slider_Pitch.value() / 100.0
			self.orien_y[self.handling_item] = self.orien_y_btn[self.handling_item] + self.Slider_Yaw.value() / 100.0

			self.Status_roll.setText("%i"%int(float(self.orien_r[self.handling_item])*180/pi))
			self.Status_pitch.setText("%i"%int(float(self.orien_p[self.handling_item])*180/pi))
			self.Status_yaw.setText("%i"%int(float(self.orien_y[self.handling_item])*180/pi))

	def change_button(self, whichbtn):
		if self.handling_item != None:
			if whichbtn == 'roll_down':
				self.orien_r[self.handling_item] = self.orien_r[self.handling_item] - pi/2
				self.orien_r_btn[self.handling_item] = self.orien_r[self.handling_item]
				self.Status_roll.setText("%i"%int(float(self.orien_r[self.handling_item])*180/pi))
			elif whichbtn == 'roll_up':
				self.orien_r[self.handling_item] = self.orien_r[self.handling_item] + pi/2
				self.orien_r_btn[self.handling_item] = self.orien_r[self.handling_item]
				self.Status_roll.setText("%i"%int(float(self.orien_r[self.handling_item])*180/pi))
			elif whichbtn == 'pitch_down':
				self.orien_p[self.handling_item] = self.orien_p[self.handling_item] - pi/2
				self.orien_p_btn[self.handling_item] = self.orien_p[self.handling_item]
				self.Status_pitch.setText("%i"%int(float(self.orien_p[self.handling_item])*180/pi))
			elif whichbtn == 'pitch_up':
				self.orien_p[self.handling_item] = self.orien_p[self.handling_item] + pi/2
				self.orien_p_btn[self.handling_item] = self.orien_p[self.handling_item]
				self.Status_pitch.setText("%i"%int(float(self.orien_p[self.handling_item])*180/pi))
			elif whichbtn == 'yaw_down':
				self.orien_y[self.handling_item] = self.orien_y[self.handling_item] - pi/2
				self.orien_y_btn[self.handling_item] = self.orien_y[self.handling_item]
				self.Status_yaw.setText("%i"%int(float(self.orien_y[self.handling_item])*180/pi))
			elif whichbtn == 'yaw_up':
				self.orien_y[self.handling_item] = self.orien_y[self.handling_item] + pi/2
				self.orien_y_btn[self.handling_item] = self.orien_y[self.handling_item]
				self.Status_yaw.setText("%i"%int(float(self.orien_y[self.handling_item])*180/pi))



	def render(self, rgb, model, R, t):
		K = self.get_camera_intrinsic()
		surf_color = (1,0,0)
		im_size = (rgb.shape[1],rgb.shape[0])
		ren_rgb = renderer.render(model, im_size, K, R, t,
								  surf_color=surf_color, mode='rgb')
		ren_gray = cv2.cvtColor(ren_rgb, cv2.COLOR_RGB2GRAY)
		mask = np.zeros((ren_gray.shape[0], ren_gray.shape[1]))
		mask[ren_gray!=0]=255
		# cv2.imwrite("/home/david/test.png",mask)
		vis_rgb = 0.4 * rgb.astype(np.float) + 0.6 * ren_rgb.astype(np.float)
		vis_rgb = vis_rgb.astype(np.uint8)

		return vis_rgb, mask

	def Quaternion2Rotation(self, Quaternion):

		rotation_vec = PyKDL.Rotation.Quaternion(Quaternion.x,Quaternion.y,Quaternion.z,Quaternion.w)
		rotation_matrix = np.zeros((3,3))

		for i in range(3):
			for j in range(3):
				rotation_matrix[i,j] = rotation_vec[i,j]

		# translation_matrix[0,0] = translation2.x * 1000
		# translation_matrix[1,0] = translation2.y * 1000
		# translation_matrix[2,0] = translation2.z * 1000
		
		return rotation_matrix


	def Quaternion2RPY(self, Quaternion, translation, original_index, marker_index):
		# print(marker_index)
		

		rotation_vec = PyKDL.Rotation.Quaternion(Quaternion.x,Quaternion.y,Quaternion.z,Quaternion.w)
		
		# rotation_vec = rotation_vec.Inverse()
		rotation_add = PyKDL.Rotation.EulerZYX(self.orien_r[original_index] + self.marker_rot[marker_index][2], self.orien_p[original_index], self.orien_y[original_index])
		# rotation_add = rotation_add.Inverse()

		# rotation_add = rotation_add.Inverse()

		rotation_matrix = np.zeros((3,3))

		for i in range(3):
			for j in range(3):
				rotation_matrix[i,j] = rotation_vec[i,j]


		rotation_matrix_add = np.zeros((3,3))

		for i in range(3):
			for j in range(3):
				rotation_matrix_add[i,j] = rotation_add[i,j]

		
		rotation_matrix_new = np.matmul(rotation_matrix, rotation_matrix_add)

		R_tmp = []

		for i in range(3):
			for j in range(3):
				R_tmp.append(rotation_matrix_new[i][j])

		rotation = PyKDL.Rotation(R_tmp[0],R_tmp[1],R_tmp[2],R_tmp[3],R_tmp[4],R_tmp[5],R_tmp[6],R_tmp[7],R_tmp[8])

		# print(marker_index)
		# rotation.DoRotZ(self.marker_rot[marker_index][2])

		# rotation_matrix_new = np.zeros((3,3))
		# for i in range(3):
		# 	for j in range(3):
		# 		rotation_matrix_new[i,j] = rotation[i,j]


		rotation_rpy = rotation.GetRPY()

		translation_matrix = np.zeros(3)
		translation_matrix[0] = (translation.x) * 1000
		translation_matrix[1] = (translation.y) * 1000
		translation_matrix[2] = (translation.z) * 1000

		translation_marker = np.zeros(3)
		translation_marker[0] = self.marker_trans[marker_index][0] * 1000
		translation_marker[1] = self.marker_trans[marker_index][1] * 1000
		translation_marker[2] = self.marker_trans[marker_index][2] * 1000

		object_translation = np.matmul(rotation_matrix, translation_marker)

		translation_add = [self.trans_x[original_index], self.trans_y[original_index], self.trans_z[original_index]]
		new_translation = np.matmul(rotation_matrix, translation_add)

		new_translation = new_translation + translation_matrix + object_translation

		translation_matrix_new = np.zeros((3,1))
		translation_matrix_new[0,0] = new_translation[0]
		translation_matrix_new[1,0] = new_translation[1]
		translation_matrix_new[2,0] = new_translation[2]

		return translation_matrix_new, rotation_matrix_new

		

	def pose1(self):
		if self.handling_item != None:
			original_index = self.handling_item
			rgb, mask = self.render(self.frame_rgb, self.model_list[original_index], self.rotation_matrix_list[original_index], self.translation_matrix_list[original_index])
			self.preview_monitor(rgb)
		# self.Progress.setValue(10)

	def grasp(self):
		if self.capture_trigger == False:
			self.capture_trigger = True
			self.capture_count = 0
		elif self.capture_trigger == True:
			self.capture_trigger = 'save'
		else:
			self.capture_trigger = False
		


	def callback_result(self,data):
		self.result = data


	def callback_rgb(self, data):
		try:
			self.frame = self.bridge.imgmsg_to_cv2(data,"bgr8")
			self.frame_rgb = cv2.cvtColor(self.frame,cv2.COLOR_BGR2RGB)
		except CvBridgeError as e:
			print(e)


	def get_camera_intrinsic(self):
		K = np.zeros((3, 3), dtype='float64')
		K[0, 0], K[0, 2] = 614.14501953125, 314.00128173828125
		K[1, 1], K[1, 2] = 614.680419921875, 242.40391540527344
		# K[0, 0], K[0, 2] = 617.099853515625, 322.427490234375
		# K[1, 1], K[1, 2] = 617.1395263671875, 237.4270782470703
		K[2, 2] = 1.
		return K

	def compute_projection(self, points_3D, transformation, internal_calibration):
		projections_2d = np.zeros((2, points_3D.shape[1]), dtype='float32')
		camera_projection = (internal_calibration.dot(transformation)).dot(points_3D)
		projections_2d[0, :] = camera_projection[0, :]/camera_projection[2, :]
		projections_2d[1, :] = camera_projection[1, :]/camera_projection[2, :]

		return projections_2d

	def get_3D_corners(self,vertices):
	
		min_x = np.min(vertices[0,:])
		max_x = np.max(vertices[0,:])
		min_y = np.min(vertices[1,:])
		max_y = np.max(vertices[1,:])
		min_z = np.min(vertices[2,:])
		max_z = np.max(vertices[2,:])

		corners = np.array([[min_x, min_y, min_z],
							[min_x, min_y, max_z],
							[min_x, max_y, min_z],
							[min_x, max_y, max_z],
							[max_x, min_y, min_z],
							[max_x, min_y, max_z],
							[max_x, max_y, min_z],
							[max_x, max_y, max_z]])

		corners = np.concatenate((np.transpose(corners), np.ones((1,8))), axis=0)
		return corners

	def callback_april(self, data):
		
		cal_status = rospy.get_param('calculation')
		if cal_status:
			pass
		else:
			self.detection = data.detections

	def detection_april(self):
		

		if self.capture_trigger != 'save':
			rospy.set_param('calculation',True)
			cal_status = rospy.get_param('calculation')
			try:
				tmp_detection = self.detection
				ids = []
				tmp_rgb = self.frame_rgb.copy()
				ori_img = self.frame_rgb.copy()
				tmp_pose = []

				for i in range(len(tmp_detection)):
					
					pos_x = tmp_detection[i].pose.pose.pose.position.x
					pos_y = tmp_detection[i].pose.pose.pose.position.y
					pos_z = tmp_detection[i].pose.pose.pose.position.z
					
					pos_xy = (self.frame_xmin,self.frame_ymin)
					real_xmin, real_ymin = self.pixel_to_tool(pos_xy)
					pos_xy = (self.frame_xmax, self.frame_ymax)
					real_xmax, real_ymax = self.pixel_to_tool(pos_xy)

					if pos_x > real_xmin and pos_x < real_xmax and pos_y > real_ymin and pos_y < real_ymax:
					# if pos_y < 0.10 and pos_y > -0.10:
						ids.append(tmp_detection[i].id[0])
						tmp_pose.append(tmp_detection[i])

				# tmp_list = []
				# for i in range(len(self.marker_list)):
				# 	tmp_val = 0
				# 	for j in range(3):
				# 		if self.marker_list[i][j] in ids:
				# 			tmp_val += 1
				# 	if tmp_val == 3:
				# 		tmp_list.append(i)

				# center_april = ids.index(self.marker_list[tmp_list[0]][1])
				# print(ids[tmp_pose.index(min(tmp_pose))])
				center_april = 0
				pose = tmp_pose[0]
				# if center_april == 0 or center_april == 6:
				# 	pose1 = tmp_detection[ids.index(3)]
				# 	pose2 = tmp_detection[ids.index(9)]

				# elif center_april == 1 or center_april == 7:
				# 	pose1 = tmp_detection[ids.index(4)]
				# 	pose2 = tmp_detection[ids.index(10)]

				# elif center_april == 2 or center_april == 8:
				# 	pose1 = tmp_detection[ids.index(5)]
				# 	pose2 = tmp_detection[ids.index(11)]

				# elif center_april == 3 or center_april == 9:
				# 	pose1 = tmp_detection[ids.index(6)]
				# 	pose2 = tmp_detection[ids.index(0)]
				
				# elif center_april == 4 or center_april == 10:
				# 	pose1 = tmp_detection[ids.index(7)]
				# 	pose2 = tmp_detection[ids.index(1)]
				
				# elif center_april == 5 or center_april == 11:
				# 	pose1 = tmp_detection[ids.index(8)]
				# 	pose2 = tmp_detection[ids.index(2)]

				# else:
				# 	self.Video_Streaming_Result.clear()
				# 	self.Video_Streaming_Result.setText("No detection")


				# if (0 in ids and 6 in ids):
				# 	print(0,6)
				# 	pose1 = tmp_detection[ids.index(0)]
				# 	pose2 = tmp_detection[ids.index(6)]
				# elif (1 in ids and 7 in ids):
				# 	print(1,7)
				# 	pose1 = tmp_detection[ids.index(1)]
				# 	pose2 = tmp_detection[ids.index(7)]
				# elif (2 in ids and 8 in ids):
				# 	print(2,8)
				# 	pose1 = tmp_detection[ids.index(2)]
				# 	pose2 = tmp_detection[ids.index(8)]
				# elif (3 in ids and 9 in ids):
				# 	print(3,9)
				# 	pose1 = tmp_detection[ids.index(3)]
				# 	pose2 = tmp_detection[ids.index(9)]
				# elif (4 in ids and 10 in ids):
				# 	print(4,10)
				# 	pose1 = tmp_detection[ids.index(4)]
				# 	pose2 = tmp_detection[ids.index(10)]
				# elif (5 in ids and 11 in ids):
				# 	print(5,11)
				# 	pose1 = tmp_detection[ids.index(5)]
				# 	pose2 = tmp_detection[ids.index(11)]
				# else:
				# 	self.Video_Streaming_Result.clear()
				# 	self.Video_Streaming_Result.setText("No detection")
					# print("No detections")

				pose = pose.pose.pose.pose

				self.translation = pose.position
				self.orientation = pose.orientation
				if len(self.activated_items) != 0:
					try:
						for i in range(len(self.activated_items)):
							
							original_index = self.objects.index(self.activated_items[i])

							translation_matrix, rotation_matrix = self.Quaternion2RPY(self.orientation, self.translation, original_index, ids[center_april])

							# rotation_matrix = self.Quaternion2Rotation(self.orientation)
							self.translation_matrix_list[original_index] = translation_matrix
							self.rotation_matrix_list[original_index] = rotation_matrix

							transformation = np.concatenate((rotation_matrix, translation_matrix), axis=1)
							
							proj_2d_gt = np.transpose(self.compute_projection(self.corners3D_list[original_index], transformation, self.internal_calibration))
							
							self.proj_2d_gt_list[original_index] = proj_2d_gt

							box_3d_color = self.color_items[i]

							################################################

							x1 = int(proj_2d_gt[0][0])
							y1 = int(proj_2d_gt[0][1])
							x2 = int(proj_2d_gt[2][0])
							y2 = int(proj_2d_gt[2][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[4][0])
							y1 = int(proj_2d_gt[4][1])
							x2 = int(proj_2d_gt[6][0])
							y2 = int(proj_2d_gt[6][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[0][0])
							y1 = int(proj_2d_gt[0][1])
							x2 = int(proj_2d_gt[4][0])
							y2 = int(proj_2d_gt[4][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[2][0])
							y1 = int(proj_2d_gt[2][1])
							x2 = int(proj_2d_gt[6][0])
							y2 = int(proj_2d_gt[6][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							################################################

							x1 = int(proj_2d_gt[1][0])
							y1 = int(proj_2d_gt[1][1])
							x2 = int(proj_2d_gt[3][0])
							y2 = int(proj_2d_gt[3][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[5][0])
							y1 = int(proj_2d_gt[5][1])
							x2 = int(proj_2d_gt[7][0])
							y2 = int(proj_2d_gt[7][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[1][0])
							y1 = int(proj_2d_gt[1][1])
							x2 = int(proj_2d_gt[5][0])
							y2 = int(proj_2d_gt[5][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[3][0])
							y1 = int(proj_2d_gt[3][1])
							x2 = int(proj_2d_gt[7][0])
							y2 = int(proj_2d_gt[7][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							################################################

							x1 = int(proj_2d_gt[0][0])
							y1 = int(proj_2d_gt[0][1])
							x2 = int(proj_2d_gt[1][0])
							y2 = int(proj_2d_gt[1][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[2][0])
							y1 = int(proj_2d_gt[2][1])
							x2 = int(proj_2d_gt[3][0])
							y2 = int(proj_2d_gt[3][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[4][0])
							y1 = int(proj_2d_gt[4][1])
							x2 = int(proj_2d_gt[5][0])
							y2 = int(proj_2d_gt[5][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[6][0])
							y1 = int(proj_2d_gt[6][1])
							x2 = int(proj_2d_gt[7][0])
							y2 = int(proj_2d_gt[7][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							################################################

							x1 = int(proj_2d_gt[1][0])
							y1 = int(proj_2d_gt[1][1])
							x2 = int(proj_2d_gt[7][0])
							y2 = int(proj_2d_gt[7][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[3][0])
							y1 = int(proj_2d_gt[3][1])
							x2 = int(proj_2d_gt[5][0])
							y2 = int(proj_2d_gt[5][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							################################################

							x1 = int(proj_2d_gt[2][0])
							y1 = int(proj_2d_gt[2][1])
							x2 = int(proj_2d_gt[7][0])
							y2 = int(proj_2d_gt[7][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)

							x1 = int(proj_2d_gt[3][0])
							y1 = int(proj_2d_gt[3][1])
							x2 = int(proj_2d_gt[6][0])
							y2 = int(proj_2d_gt[6][1])
							cv2.line(ori_img,(x1,y1),(x2,y2),box_3d_color,2)
					except:
						pass
				self.frame_result = ori_img.copy()
				self.result_monitor(ori_img)

				if self.capture_trigger:
					rotation_matrix = []
					translation_matrix = []
					proj_2d_gt_tmp = []

					for i in range(len(self.activated_items)):
						rotation_matrix.append(self.rotation_matrix_list[self.objects.index(self.activated_items[i])])
						translation_matrix.append(self.translation_matrix_list[self.objects.index(self.activated_items[i])])
						proj_2d_gt_tmp.append(self.proj_2d_gt_list[self.objects.index(self.activated_items[i])])

					self.capture_count += 1
					self.Progress.setValue(0)
					self.rgb_save.append(tmp_rgb)
					self.rotation_save.append(rotation_matrix)
					# self.depth_save.append(self.depth_origin)
					self.translation_save.append(translation_matrix)
					ori_img = cv2.cvtColor(ori_img, cv2.COLOR_RGB2BGR)
					self.inspection_save.append(ori_img)
					self.proj_2d_gt_save.append(proj_2d_gt_tmp)
					self.Status.setText("Capturing..(%i images)"%len(self.rgb_save))
					if self.capture_count == 125:
						self.capture_trigger = 'save'
			except:
				pass
			rospy.set_param('calculation',False)

		elif self.capture_trigger == 'save':
			progress_value = 0
			number_of_files = float(len(self.rgb_save))
			for i in range(len(self.rgb_save)):
				progress_value = (i / number_of_files) * 100.0
				self.Progress.setValue(progress_value)
				self.save_results(i)
				self.Status.setText("Saving.. (%s/%s)"%(i,len(self.rgb_save)))
			self.Progress.setValue(100)
			self.Status.setText("Images are saved successfully.")
			self.capture_trigger = False

			self.rgb_save = []
			self.depth_save = []
			self.rotation_save = []
			self.translation_save = []
			self.inspection_save = []
			self.proj_2d_gt_save = []

	def start(self):
		self.timer = QTimer()
		self.timer.timeout.connect(self.streaming_start)
		self.timer.start(1000/10)

	def streaming_start(self):
		status = rospy.get_param('calculation')
		if status:
			pass
		else:
			self.detection_april()
		frame = self.frame_rgb.copy()
		guide_width = self.guide_width + self.roi_width
		guide_height = self.guide_height + self.roi_height
		guide_xcen = self.guide_xcen + self.roi_x
		guide_ycen = self.guide_ycen - self.roi_y
		self.frame_xmin = guide_xcen-guide_width
		self.frame_xmax = guide_xcen+guide_width
		self.frame_ymin = guide_ycen-guide_height
		self.frame_ymax = guide_ycen+guide_height
		cv2.rectangle(frame, (self.frame_xmin,self.frame_ymin), (self.frame_xmax,self.frame_ymax), (255,0,0), 2)
		frame = cv2.resize(frame,(216,162))
		self.image = QtGui.QImage(frame, frame.shape[1], frame.shape[0], QImage.Format_RGB888)
		self.pixmapImage = QtGui.QPixmap.fromImage(self.image)
		self.Video_Streaming.setPixmap(self.pixmapImage)

	def callback_depth(self, data):
		try:
			self.depth_origin = self.bridge.imgmsg_to_cv2(data,"passthrough")
			
		except CvBridgeError as e:
			print(e)
		# self.pose1()

	def result_monitor(self, img):
		result = img
		result = cv2.resize(result,(384,288))
		self.result_image = QtGui.QImage(result, result.shape[1], result.shape[0], QImage.Format_RGB888)
		self.pixmapImage_result = QtGui.QPixmap.fromImage(self.result_image)
		self.Video_Streaming_Result.setPixmap(self.pixmapImage_result)

	def preview_monitor(self, img):
		result = img
		result = cv2.resize(result,(384,288))
		self.preview_image = QtGui.QImage(result, result.shape[1], result.shape[0], QImage.Format_RGB888)
		self.pixmapImage_preview = QtGui.QPixmap.fromImage(self.preview_image)
		self.Video_Streaming_Preview.setPixmap(self.pixmapImage_preview)

	def ROI_x_change(self):
		self.roi_x = self.roi_x_value.value()
		print(self.roi_x)

	def ROI_y_change(self):
		self.roi_y = self.roi_y_value.value()
		print(self.roi_y)

	def ROI_width_change(self):
		self.roi_width = self.roi_width_value.value()
		print(self.roi_width)

	def ROI_height_change(self):
		self.roi_height = self.roi_height_value.value()
		print(self.roi_height)


	def pixel_to_tool(self, pos):
		self.x_pix = pos[0]
		self.y_pix = pos[1]
		self.z_rgb = self.z_cam_to_tool * 1000
		x_rgb = self.z_rgb*(self.x_pix-self.ppx)/self.fu
		y_rgb = self.z_rgb*(self.y_pix-self.ppy)/self.fv
		x = x_rgb
		y = y_rgb
		# z = z_rgb - 184.0
		return x/1000, y/1000


	def save_results(self, count):		

		for index in range(len(self.activated_items)):
			original_index = self.objects.index(self.activated_items[index])

			if not os.path.isdir("%s/%s/JPEGImages"%(self.save_path,self.objects[original_index])):
				os.makedirs("%s/%s/JPEGImages"%(self.save_path,self.objects[original_index]))
			# if not os.path.isdir("%s/%s/mask"%(self.save_path,self.objects[original_index])):
			# 	os.makedirs("%s/%s/mask"%(self.save_path,self.objects[original_index]))
			# if not os.path.isdir("%s/%s/labels"%(self.save_path,self.objects[original_index])):
			# 	os.makedirs("%s/%s/labels"%(self.save_path,self.objects[original_index]))
			if not os.path.isdir("%s/%s/inspection"%(self.save_path,self.objects[original_index])):
				os.makedirs("%s/%s/inspection"%(self.save_path,self.objects[original_index]))
			# if not os.path.isdir("%s/%s/changed_img"%(self.save_path,self.objects[original_index])):
			# 	os.makedirs("%s/%s/changed_img"%(self.save_path,self.objects[original_index]))
			if not os.path.isdir("%s/%s/rotation"%(self.save_path,self.objects[original_index])):
				os.makedirs("%s/%s/rotation"%(self.save_path,self.objects[original_index]))
			if not os.path.isdir("%s/%s/translation"%(self.save_path,self.objects[original_index])):
				os.makedirs("%s/%s/translation"%(self.save_path,self.objects[original_index]))
			# if not os.path.isdir("%s/%s/depth"%(self.save_path,self.objects[original_index])):
			# 	os.makedirs("%s/%s/depth"%(self.save_path,self.objects[original_index]))

			tmp_bgr = cv2.cvtColor(self.rgb_save[count], cv2.COLOR_RGB2BGR)
			cv2.imwrite("%s/%s/JPEGImages/%.6i.png"%(self.save_path,self.objects[original_index],self.save_count),tmp_bgr)
			# cv2.imwrite("%s/%s/mask/%.4i.png"%(self.save_path,self.objects[original_index],self.save_count),mask)
			cv2.imwrite("%s/%s/inspection/ins%i.png"%(self.save_path,self.objects[original_index],self.save_count), self.inspection_save[count])
			# cv2.imwrite("%s/%s/changed_img/%.6i.png"%(self.save_path,self.objects[original_index],self.save_count), result_dummy)

			np.save("%s/%s/rotation/%.6i.npy"%(self.save_path,self.objects[original_index],self.save_count), self.rotation_save[count][index])
			np.save("%s/%s/translation/%.6i.npy"%(self.save_path,self.objects[original_index],self.save_count), self.translation_save[count][index])
			# np.save("%s/%s/depth/%.6i.npy"%(self.save_path,self.objects[original_index],self.save_count), self.depth_save[count])

			# rospy.sleep(0.1)
		self.save_count += 1


def main(args):
	rospy.init_node('UR5_UI', anonymous=True)

if __name__=='__main__':
	main(sys.argv)
	app = QApplication(sys.argv)
	widget = UR5_UI()
	widget.show()
	sys.exit(app.exec_())
