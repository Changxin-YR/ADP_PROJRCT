import { StyleSheet } from 'react-native';
import { spacing, borderRadius, shadows, typography } from './index';

export const CommonStyles = StyleSheet.create({
  screenContainer: {
    flex: 1,
  },
  contentContainer: {
    padding: spacing.lg,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  card: {
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
    ...shadows.md,
  },
  sectionTitle: {
    ...typography.title3,
    marginBottom: spacing.md,
  },
  listSeparator: {
    height: StyleSheet.hairlineWidth,
    marginLeft: spacing.lg,
  },
});
