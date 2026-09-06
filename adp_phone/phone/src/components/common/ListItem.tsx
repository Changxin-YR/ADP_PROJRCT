import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../../theme';

interface ListItemProps {
  title: string;
  subtitle?: string;
  leftIcon?: keyof typeof Ionicons.glyphMap;
  leftIconColor?: string;
  leftIconBgColor?: string;
  rightText?: string;
  rightElement?: React.ReactNode;
  showChevron?: boolean;
  onPress?: () => void;
  style?: ViewStyle;
  compact?: boolean;
}

export const ListItem: React.FC<ListItemProps> = ({
  title,
  subtitle,
  leftIcon,
  leftIconColor = colors.primary,
  leftIconBgColor,
  rightText,
  rightElement,
  showChevron = true,
  onPress,
  style,
  compact = false,
}) => {
  const content = (
    <View style={[styles.container, compact && styles.compact, style]}>
      {leftIcon && (
        <View
          style={[
            styles.iconContainer,
            { backgroundColor: leftIconBgColor || leftIconColor + '15' },
          ]}
        >
          <Ionicons name={leftIcon} size={20} color={leftIconColor} />
        </View>
      )}
      <View style={styles.content}>
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
        {subtitle && (
          <Text style={styles.subtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        )}
      </View>
      {rightText && <Text style={styles.rightText}>{rightText}</Text>}
      {rightElement}
      {showChevron && (
        <Ionicons name="chevron-forward" size={18} color={colors.gray3} style={styles.chevron} />
      )}
    </View>
  );

  if (onPress) {
    return (
      <TouchableOpacity onPress={onPress} activeOpacity={0.6}>
        {content}
      </TouchableOpacity>
    );
  }
  return content;
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.base,
    minHeight: 56,
  },
  compact: {
    minHeight: 44,
    paddingVertical: spacing.sm,
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.md,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
  },
  title: {
    ...typography.body,
    color: colors.text,
  },
  subtitle: {
    ...typography.caption1,
    color: colors.textTertiary,
    marginTop: 2,
  },
  rightText: {
    ...typography.subhead,
    color: colors.textTertiary,
    marginRight: spacing.xs,
  },
  chevron: {
    marginLeft: spacing.xs,
  },
});

export default ListItem;
