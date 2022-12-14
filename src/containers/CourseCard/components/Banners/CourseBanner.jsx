/* eslint-disable max-len */
import React from 'react';
import PropTypes from 'prop-types';
import { Hyperlink } from '@edx/paragon';
import { useIntl } from '@edx/frontend-platform/i18n';

import { hooks as appHooks } from 'data/redux';
import Banner from 'components/Banner';
import messages from './messages';

export const CourseBanner = ({ courseNumber }) => {
  const {
    isVerified,
    isAuditAccessExpired,
    canUpgrade,
  } = appHooks.useCardEnrollmentData(courseNumber);
  const courseRun = appHooks.useCardCourseRunData(courseNumber);
  const course = appHooks.useCardCourseData(courseNumber);
  const { formatMessage } = useIntl();

  if (isVerified) { return null; }

  if (isAuditAccessExpired) {
    if (canUpgrade) {
      return (
        <Banner>
          {formatMessage(messages.auditAccessExpired)}
          {'  '}
          {formatMessage(messages.upgradeToAccess)}
        </Banner>
      );
    }
    return (
      <Banner>
        {formatMessage(messages.auditAccessExpired)}
        {'  '}
        <Hyperlink destination="">{formatMessage(messages.findAnotherCourse)}</Hyperlink>
      </Banner>
    );
  }
  if (courseRun.isActive && !canUpgrade) {
    return (
      <Banner>
        {formatMessage(messages.upgradeDeadlinePassed)}
        {'  '}
        <Hyperlink destination={course.website || ''}>
          {formatMessage(messages.exploreCourseDetails)}
        </Hyperlink>
      </Banner>
    );
  }
  return null;
};
CourseBanner.propTypes = {
  courseNumber: PropTypes.string.isRequired,
};

export default CourseBanner;
