# Copyright (c) 2015, Frappe Technologies and Contributors
# See license.txt

import unittest

import frappe

from education.education.doctype.topic.test_topic import (
    make_topic, make_topic_and_linked_content)

# test_records = frappe.get_test_records('Course')


class TestCourseLMSSync(unittest.TestCase):
	"""Tests for bidirectional sync between Education Course and LMS Course."""

	def setUp(self):
		self._cleanup = []  # list of (doctype, name) in creation order

	def tearDown(self):
		# Delete in reverse creation order; LMS Course added after Education Course
		# so it is deleted first (reversed), clearing backlinks before parent deletion
		for doctype, name in reversed(self._cleanup):
			if frappe.db.exists(doctype, name):
				try:
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
				except Exception:
					pass
		frappe.db.commit()

	def _skip_if_no_lms(self):
		if "lms" not in frappe.get_installed_apps():
			self.skipTest("LMS app not installed")

	def _make_topic(self, name):
		if frappe.db.exists("Topic", name):
			return frappe.get_doc("Topic", name)
		topic = frappe.get_doc({"doctype": "Topic", "topic_name": name}).insert(
			ignore_permissions=True
		)
		self._cleanup.append(("Topic", topic.name))
		return topic

	def _make_edu_course(self, name, topics=None):
		course = frappe.new_doc("Course")
		course.course_name = name
		if topics:
			for t in topics:
				course.append("topics", {"topic": t})
		course.insert(ignore_permissions=True)
		self._cleanup.append(("Course", course.name))
		return course

	def test_edu_course_creates_lms_course(self):
		"""Saving an Education Course should auto-create a linked LMS Course."""
		self._skip_if_no_lms()

		course = self._make_edu_course(f"_Test Sync {frappe.generate_hash()[:8]}")
		lms_name = frappe.db.get_value("Course", course.name, "lms_course")

		self.assertTrue(lms_name, "LMS Course was not created when Education Course was saved")
		self._cleanup.append(("LMS Course", lms_name))

		lms = frappe.get_doc("LMS Course", lms_name)
		self.assertEqual(lms.title, course.course_name)
		self.assertEqual(lms.education_course, course.name)

	def test_edu_course_update_syncs_to_lms(self):
		"""Updating an Education Course should update the linked LMS Course."""
		self._skip_if_no_lms()

		course = self._make_edu_course(f"_Test Update {frappe.generate_hash()[:8]}")
		lms_name = frappe.db.get_value("Course", course.name, "lms_course")
		self._cleanup.append(("LMS Course", lms_name))

		course.description = "Updated from Education"
		course.save()

		lms = frappe.get_doc("LMS Course", lms_name)
		self.assertEqual(lms.short_introduction, "Updated from Education")

	def test_edu_topics_sync_to_lms_chapters(self):
		"""Education Course topics should appear as LMS Course chapters after save."""
		self._skip_if_no_lms()

		t1 = self._make_topic(f"_Sync Topic A {frappe.generate_hash()[:6]}")
		t2 = self._make_topic(f"_Sync Topic B {frappe.generate_hash()[:6]}")

		course = self._make_edu_course(
			f"_Test Topics {frappe.generate_hash()[:8]}", topics=[t1.name, t2.name]
		)
		lms_name = frappe.db.get_value("Course", course.name, "lms_course")
		self._cleanup.append(("LMS Course", lms_name))

		chapter_titles = frappe.db.get_all("Course Chapter", {"course": lms_name}, pluck="title")
		self.assertIn(t1.topic_name, chapter_titles)
		self.assertIn(t2.topic_name, chapter_titles)

		for ch in frappe.get_all("Course Chapter", {"course": lms_name}):
			self._cleanup.append(("Course Chapter", ch.name))

	def test_no_infinite_sync_loop(self):
		"""Saving an Education Course must not recurse into an infinite sync loop."""
		self._skip_if_no_lms()

		course = self._make_edu_course(f"_Test Loop {frappe.generate_hash()[:8]}")
		lms_name = frappe.db.get_value("Course", course.name, "lms_course")
		self._cleanup.append(("LMS Course", lms_name))

		# Second save should complete without recursion or error
		course.description = "loop check"
		course.save()

		# Both docs should still be intact
		self.assertTrue(frappe.db.exists("Course", course.name))
		self.assertTrue(frappe.db.exists("LMS Course", lms_name))


class TestCourse(unittest.TestCase):
	def setUp(self):
		make_topic_and_linked_content(
			"_Test Topic 1", [{"type": "Article", "name": "_Test Article 1"}]
		)
		make_topic_and_linked_content(
			"_Test Topic 2", [{"type": "Article", "name": "_Test Article 2"}]
		)
		make_course_and_linked_topic("_Test Course 1", ["_Test Topic 1", "_Test Topic 2"])

	def test_get_topics(self):
		course = frappe.get_doc("Course", "_Test Course 1")
		topics = course.get_topics()
		self.assertEqual(topics[0].name, "_Test Topic 1")
		self.assertEqual(topics[1].name, "_Test Topic 2")
		frappe.db.rollback()


def make_course(name):
	try:
		course = frappe.get_doc("Course", name)
	except frappe.DoesNotExistError:
		course = frappe.get_doc(
			{"doctype": "Course", "course_name": name, "course_code": name}
		).insert()
	return course.name


def make_course_and_linked_topic(course_name, topic_name_list):
	try:
		course = frappe.get_doc("Course", course_name)
	except frappe.DoesNotExistError:
		make_course(course_name)
		course = frappe.get_doc("Course", course_name)
	topic_list = [make_topic(topic_name) for topic_name in topic_name_list]
	for topic in topic_list:
		course.append("topics", {"topic": topic})
	course.save()
	return course
