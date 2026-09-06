import React from 'react';
import { View, Text, StyleSheet, ViewStyle } from 'react-native';
import { colors, typography, borderRadius, spacing } from '../../theme';

interface BadgeProps {
  label: string;
  color?: string;
  backgroundColor?: string;
  size?: 'sm' | 'md';
  style?: ViewStyle;
}

export const Badge: React.FC<BadgeProps> = ({
  label,
  color,
  backgroundColor,
  size = 'sm',
  style,
}) => {
  const badgeColor = color || colors.primary;
  const bgColor = backgroundColor || badgeColor + '18';

  return (
    <View style={[styles.container, styles[size], { backgroundColor: bgColor }, style]}>
      <Text style={[styles.text, styles[`text_${size}`], { color: badgeColor }]}>
        {label}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: borderRadius.full,
  },
  sm: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  md: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  text: {
    fontWeight: '600',
  },
  text_sm: {
    ...typography.caption2,
    fontWeight: '600',
  },
  text_md: {
    ...typography.caption1,
    fontWeight: '600',
  },
});

export default Badge;
