# Copyright (c) 2015, Frappe Technologies and contributors
# For license information, please see license.txt


import json

import frappe
from frappe import _
from frappe.model.document import Document


class Course(Document):
	def validate(self):
		self.validate_assessment_criteria()

	def on_update(self):
		if frappe.flags.in_lms_sync:
			return
		if frappe.db.table_exists("tabLMS Course"):
			self.sync_to_lms()

	def sync_to_lms(self):
		frappe.flags.in_lms_sync = True
		try:
			is_new = not self.lms_course
			if not is_new:
				lms_doc = frappe.get_doc("LMS Course", self.lms_course)
			else:
				lms_doc = frappe.new_doc("LMS Course")
				lms_doc.flags.ignore_mandatory = True

			lms_doc.title = self.course_name
			lms_doc.description = self.description or self.course_name
			lms_doc.short_introduction = self.description or self.course_name
			lms_doc.image = self.hero_image
			lms_doc.education_course = self.name

			if is_new:
				lms_doc.insert(ignore_permissions=True)
				frappe.db.set_value("Course", self.name, "lms_course", lms_doc.name, update_modified=False)
			else:
				lms_doc.save(ignore_permissions=True)

			self._sync_topics_to_chapters(lms_doc)
		finally:
			frappe.flags.in_lms_sync = False

	def _sync_topics_to_chapters(self, lms_doc):
		existing_titles = set(
			frappe.db.get_value("Course Chapter", ref.chapter, "title")
			for ref in frappe.get_all("Chapter Reference", {"parent": lms_doc.name}, ["chapter"])
			if ref.chapter
		)

		for topic_row in self.topics:
			if not topic_row.topic:
				continue
			topic_name = frappe.db.get_value("Topic", topic_row.topic, "topic_name")
			if not topic_name or topic_name in existing_titles:
				continue

			chapter = frappe.new_doc("Course Chapter")
			chapter.title = topic_name
			chapter.course = lms_doc.name
			chapter.insert(ignore_permissions=True)

			frappe.get_doc({
				"doctype": "Chapter Reference",
				"chapter": chapter.name,
				"parent": lms_doc.name,
				"parentfield": "chapters",
				"parenttype": "LMS Course",
			}).insert(ignore_permissions=True)

			existing_titles.add(topic_name)

	def validate_assessment_criteria(self):
		if self.assessment_criteria:
			total_weightage = 0
			for criteria in self.assessment_criteria:
				total_weightage += criteria.weightage or 0
			if total_weightage != 100:
				frappe.throw(_("Total Weightage of all Assessment Criteria must be 100%"))

	def get_topics(self):
		topic_data = []
		for topic in self.topics:
			topic_doc = frappe.get_doc("Topic", topic.topic)
			if topic_doc.topic_content:
				topic_data.append(topic_doc)
		return topic_data


@frappe.whitelist()
def add_course_to_programs(course, programs, mandatory=False):
	programs = json.loads(programs)
	for entry in programs:
		program = frappe.get_doc("Program", entry)
		program.append(
			"courses", {"course": course, "course_name": course, "mandatory": mandatory}
		)
		program.flags.ignore_mandatory = True
		program.save()
	frappe.msgprint(
		_("Course {0} has been added to all the selected programs successfully.").format(
			frappe.bold(course)
		),
		title=_("Programs updated"),
		indicator="green",
	)


@frappe.whitelist()
def get_programs_without_course(course):
	data = []
	for entry in frappe.db.get_all("Program"):
		program = frappe.get_doc("Program", entry.name)
		courses = [c.course for c in program.courses]
		if not courses or course not in courses:
			data.append(program.name)
	return data
