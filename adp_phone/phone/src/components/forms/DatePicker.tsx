import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  ViewStyle,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, typography, borderRadius, spacing } from '../../theme';

interface DatePickerFieldProps {
  label?: string;
  value?: string;
  placeholder?: string;
  onChange: (date: string) => void;
  error?: string;
  required?: boolean;
  containerStyle?: ViewStyle;
}

export const DatePickerField: React.FC<DatePickerFieldProps> = ({
  label,
  value,
  placeholder = '选择日期',
  onChange,
  error,
  required,
  containerStyle,
}) => {
  const [showPicker, setShowPicker] = useState(false);

  const formatDisplayDate = (dateStr?: string) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  };

  const generateDates = () => {
    const dates: string[] = [];
    const today = new Date();
    for (let i = -30; i <= 30; i++) {
      const d = new Date(today);
      d.setDate(today.getDate() + i);
      dates.push(d.toISOString().split('T')[0]);
    }
    return dates;
  };

  return (
    <View style={[styles.container, containerStyle]}>
      {label && (
        <Text style={styles.label}>
          {label}
          {required && <Text style={styles.required}> *</Text>}
        </Text>
      )}
      <TouchableOpacity
        style={[styles.selectButton, error && styles.selectError]}
        onPress={() => setShowPicker(true)}
        activeOpacity={0.7}
      >
        <Ionicons name="calendar-outline" size={20} color={colors.gray2} style={styles.icon} />
        <Text style={[styles.selectText, !value && styles.placeholder]}>
          {value ? formatDisplayDate(value) : placeholder}
        </Text>
      </TouchableOpacity>
      {error && <Text style={styles.error}>{error}</Text>}

      <Modal
        visible={showPicker}
        animationType="slide"
        transparent
        onRequestClose={() => setShowPicker(false)}
      >
        <TouchableOpacity
          style={styles.overlay}
          activeOpacity={1}
          onPress={() => setShowPicker(false)}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalTitle}>Select Date</Text>
            <View style={styles.dateGrid}>
              {generateDates().map((dateStr) => {
                const d = new Date(dateStr);
                const isSelected = value === dateStr;
                const isToday = dateStr === new Date().toISOString().split('T')[0];
                return (
                  <TouchableOpacity
                    key={dateStr}
                    style={[
                      styles.dateCell,
                      isSelected && styles.dateCellSelected,
                      isToday && !isSelected && styles.dateCellToday,
                    ]}
                    onPress={() => {
                      onChange(dateStr);
                      setShowPicker(false);
                    }}
                  >
                    <Text
                      style={[
                        styles.dateDay,
                        isSelected && styles.dateDaySelected,
                      ]}
                    >
                      {d.getDate()}
                    </Text>
                    <Text
                      style={[
                        styles.dateMonth,
                        isSelected && styles.dateMonthSelected,
                      ]}
                    >
                      {d.toLocaleDateString('en', { month: 'short' })}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginBottom: spacing.base,
  },
  label: {
    ...typography.subhead,
    fontWeight: '500',
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  required: {
    color: colors.error,
  },
  selectButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.backgroundSecondary,
    borderRadius: borderRadius.lg,
    borderWidth: 1.5,
    borderColor: 'transparent',
    paddingHorizontal: spacing.base,
    minHeight: 48,
  },
  selectError: {
    borderColor: colors.error,
  },
  icon: {
    marginRight: spacing.sm,
  },
  selectText: {
    ...typography.body,
    color: colors.text,
    flex: 1,
  },
  placeholder: {
    color: colors.gray2,
  },
  error: {
    ...typography.caption1,
    color: colors.error,
    marginTop: spacing.xs,
  },
  overlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  modalContent: {
    backgroundColor: colors.background,
    borderTopLeftRadius: borderRadius.xl,
    borderTopRightRadius: borderRadius.xl,
    paddingBottom: 34,
    maxHeight: '70%',
  },
  modalHandle: {
    width: 36,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: colors.gray4,
    alignSelf: 'center',
    marginTop: spacing.sm,
    marginBottom: spacing.base,
  },
  modalTitle: {
    ...typography.headline,
    color: colors.text,
    textAlign: 'center',
    marginBottom: spacing.base,
  },
  dateGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: spacing.base,
    justifyContent: 'center',
  },
  dateCell: {
    width: 48,
    height: 56,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: borderRadius.md,
    margin: 4,
  },
  dateCellSelected: {
    backgroundColor: colors.primary,
  },
  dateCellToday: {
    backgroundColor: colors.primary + '15',
  },
  dateDay: {
    ...typography.headline,
    color: colors.text,
  },
  dateDaySelected: {
    color: colors.textInverse,
  },
  dateMonth: {
    ...typography.caption2,
    color: colors.textTertiary,
    marginTop: 2,
  },
  dateMonthSelected: {
    color: colors.textInverse,
  },
});

export default DatePickerField;
