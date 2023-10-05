import logging
import pyotp
import requests
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from common.djangoapps.util.json_request import JsonResponse
from django.utils.translation import ugettext_lazy as _
from common.djangoapps.edxmako.shortcuts import render_to_response
from rest_framework import status
from common.djangoapps.student.helpers import get_next_url_for_login_page
from openedx.features.user_activity.views import export_user_activity

from .models import ExtraInfo
log = logging.getLogger(__name__)

from lms.djangoapps.payment_app_tabby.models import TabbyPaymentTable
import xlsxwriter
from django.conf import settings
from datetime import datetime, time
from django.http import HttpResponse
from io import BytesIO as IO
from django.http import HttpResponseNotFound
# USER_MODEL = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')

class UserExportData(View):
    
    @method_decorator(login_required)
    def get(self, request):

        if request.user.is_staff:
            excel_file = IO()
            workbook = xlsxwriter.Workbook(excel_file, {'in_memory': True, 'remove_timezone': True, 'default_date_format':
                                                    'dd/mm/yyyy hh:mm AM/PM'})
            worksheet = workbook.add_worksheet()

            # Start from the first cell.
            # Rows and columns are zero indexed.
            row = 0
            column = 0

            content = ['name', 'email', 'National id', 'date of registration']
            today = datetime.today()
            today = datetime.now().date()
            today = datetime.combine(today, time())
            payments = ExtraInfo.objects.filter(user__date_joined__gte=today).values_list('user__profile__name', 'user__email', 'national_id', 'user__date_joined')

            # iterating through content list
            for item in content :

                # write operation perform
                worksheet.write(row, column, item)

                # incrementing the value of column by one
                # with each iterations.
                column += 1

            column = 0
            row = 1
            for payment_item in payments:
                for i in range(len(payment_item)):
                    worksheet.write(row, column, payment_item[i])
                    column += 1
                row += 1
                column = 0

            workbook.close()
            excel_file.seek(0)
            response = HttpResponse(excel_file.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = 'attachment; filename=payment-report.xlsx'

            return response
        else:
            return HttpResponseNotFound()


class ValidateNumberView(View):

    # OTP verification timeout seconds
    interval = 60 * 10

    @method_decorator(login_required)
    def get(self, request):

        user = self.request.user

        try:
            number = user.extrainfo.number
            context = {
                "number": number,
                "is_number_verified": False,
            }
            if user.extrainfo.is_number_verified:
                context.update({"is_number_verified": True})
                return render_to_response('validate_number/validate_number.html', context)
            otp = user.extrainfo.otp
            activation_key = user.extrainfo.activation_key
            verify = False
            if activation_key:
                totp = pyotp.TOTP(activation_key, interval=self.interval)
                verify = totp.verify(otp)
            if not verify:
                key = generateKey.returnValue(self.interval)
                related_user = ExtraInfo.objects.get(user=user)
                related_user.otp = key['OTP']
                related_user.activation_key = key['totp']
                related_user.save()
                number = related_user.number
                send_sms(msg=key['OTP'], number=number)
            return render_to_response('validate_number/validate_number.html', context)

        except AttributeError as e:
            log.error(e)
            return JsonResponse({
                "success": False,
                "error": "number does not exist for given user."
            })
        except Exception as e:
            log.error(e)
            return JsonResponse({
                "success": False,
                "error": "Something went wrong"
            })

    @method_decorator(login_required)
    def post(self, request):

        try:

            otp = request.POST.get("otp")
            user = self.request.user
            _otp = user.extrainfo.otp
            if otp != _otp:

                # POST mobile_activation activity to third party API
                export_user_activity(
                    user=request.user,
                    activity_type_id="mobile_activation",
                    activity_status_id="failed",
                    description="user visited validate-number page.",
                    details="user tried to verify mobile number ({})".format(user.extrainfo.number)

                    ) #for failed mobile number validation

                return JsonResponse({"error": "otp غير صالحة"}, status=status.HTTP_406_NOT_ACCEPTABLE)
            else:
                activation_key = user.extrainfo.activation_key
                totp = pyotp.TOTP(activation_key, interval=self.interval)
                verify = totp.verify(otp)
                if verify:
                    related_user = ExtraInfo.objects.get(user=user)
                    related_user.is_number_verified = True
                    related_user.save()
                    redirect_to = get_next_url_for_login_page(request)

                    # POST mobile_activation activity to third party API
                    export_user_activity(
                        user=request.user,
                        activity_type_id="mobile_activation",
                        activity_status_id="success",
                        description="user visited validate-number page.",
                        details="user verified mobile number ({})".format(related_user.number)
                        ) #for successfully validating mobile number

                    return JsonResponse({"success": "Your number has been successfully Verified!!","redirect_to":redirect_to}, status=status.HTTP_202_ACCEPTED)
                else:
                    return JsonResponse({"error": "انتهت صلاحية كلمة المرور المؤقتة"}, status=status.HTTP_408_REQUEST_TIMEOUT)

        except Exception as e:
            log.error(e)
            return JsonResponse({"error": "Invalid otp OR No any inactive user found for given otp"}, status=status.HTTP_400_BAD_REQUEST)


class generateKey:
    @staticmethod
    def returnValue(interval):
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret, interval=interval)
        OTP = totp.now()
        return {"totp": secret, "OTP": OTP}


class ResendOTPView(View):
    interval = 60 * 10

    @method_decorator(login_required)
    def post(self, request):

        try:
            user = self.request.user
            number = user.extrainfo.number
            msg = user.extrainfo.otp
            otp = user.extrainfo.otp
            activation_key = user.extrainfo.activation_key
            if user.extrainfo.is_number_verified:
                return JsonResponse({'success': False})
            verify = False
            if activation_key:
                totp = pyotp.TOTP(activation_key, interval=self.interval)
                # check whether generated otp is expired or not
                verify = totp.verify(otp)
            if not verify:
                # Generate new otp as current otp is expired
                key = generateKey.returnValue(self.interval)
                related_user = ExtraInfo.objects.get(user=user)
                related_user.otp = key['OTP']
                related_user.activation_key = key['totp']
                related_user.save()
            if msg:
                # no matter otp is expired or not send_sms again as user has requested.
                # Currently sms api does not send again sms(with same otp) in a while if last sms was delivered.
                send_sms(msg=msg, number=number)
                return JsonResponse({"success": True})
            return JsonResponse({"success": False})
        except Exception as e:
            log.error(e)
            return JsonResponse({"success": False})


def send_sms(msg, number):
    """
    Function to send SMS to given number
    """
    try:
        text = "رمز التحقق الخاص بك هو ({}) صالح لمدة 10 دقائق فقط.".format(msg)
        #text = ".رمز المرور لمرة واحدة الخاص بك هو {msg}. رمز المرور لمرة واحدة صالح لمدة 10 دقائق فقط".format(msg=msg)
        #text = " OTP رمز المرور لمرة واحدة الخاصة بك هو {msg} رمز المرور لمرة واحدة صالح لمدة 10 دقائق فقط.".format(msg=msg)
        url = "https://basic.unifonic.com/wrapper/sendSMS.php?appsid=xIuFluYxqRAYdbxbzwIXWEvbuZGmm0&msg={msg}&to={number}&sender=TETCO&baseEncode=False&encoding=UCS2".format(msg=text, number=number)
        payload = {}
        headers = {}
        response = requests.request("GET", url, headers=headers, data=payload)
        return
    except Exception as e:
        log.error(e)

from io import BytesIO as IO
import xlsxwriter
from xmodule.modulestore.django import modulestore
from openedx.core.djangoapps.models.course_details import CourseDetails
from django.http import HttpResponse
from django.http import HttpResponseNotFound

import json
excel_file = IO()
def course_content(request):
    if request.user.is_authenticated and request.user.is_superuser:
        workbook = xlsxwriter.Workbook(excel_file, {'in_memory': True, 'remove_timezone': True, 'default_date_format':'dd/mm/yyyy hh:mm AM/PM'})
        worksheet = workbook.add_worksheet()

        row = 0
        column = 0

        content = ['index', 'display_name', 'course-code', 'course_price', 'course_type', 'ka_sub_ka', 'self-paced', 'start', 'end', 'short-description', 'efforts', 'targeted_for','powered_by_hadaf','language','cert_release']

        store = modulestore()
        courses = modulestore().get_courses()

        # iterating through content list
        for item in content :

            # write operation perform
            worksheet.write(row, column, item)
            # incrementing the value of column by one
            # with each iterations.
            column += 1

        column = 1
        row = 1

        for course in courses:
            worksheet.write(row, 0, row)
            for i in range(len(content)):
                try:
                    if i == 0:
                        worksheet.write(row, column, course.display_name_with_default)
                    elif i == 1:
                        worksheet.write(row, column, course.course_id.run)
                    elif i == 2:
                        worksheet.write(row, column, course.course_price)
                    elif i == 3:
                        worksheet.write(row, column, course.course_type)
                    elif i ==4:
                        worksheet.write(row, column, json.dumps(course.ka_sub_ka))
                    elif i ==5:
                        worksheet.write(row, column, "True" if course.course_type=='SP' else "False")
                    elif i ==6:
                        worksheet.write(row, column, course.start)
                    elif i ==7:
                        worksheet.write(row, column, course.end)
                    elif i ==8:
                        worksheet.write(row, column, CourseDetails.fetch_about_attribute(course.course_id, 'short_description'))
                    elif i ==9:
                        worksheet.write(row, column, CourseDetails.fetch_about_attribute(course.course_id, 'effort'))
                    elif i ==10:
                        worksheet.write(row, column, json.dumps(course.targeted_for))
                    elif i ==11:
                        worksheet.write(row, column, "True" if course.powered_by_hadaf else "False")
                    elif i ==12:
                        worksheet.write(row, column, course.language)
                    elif i ==13:
                        worksheet.write(row, column, course.cert_release)
                except Exception as e:
                    pass
                column += 1
            row += 1
            column = 1

        workbook.close()
        excel_file.seek(0)
        response = HttpResponse(excel_file.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=course-content.xlsx'

        return response
    else:
        return HttpResponseNotFound()
