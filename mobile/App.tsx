import { useEffect, useState } from 'react'
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native'
import { StatusBar } from 'expo-status-bar'

type Summary = { date_label?: string; kpis?: { ponds: number | null; active_batches: number | null; current_stock: number | null; todo_open: number } }

const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? 'http://127.0.0.1:5000'

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/workbench/summary`, { credentials: 'include' })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
      .then((body) => setSummary(body.data ?? body))
      .catch((reason: Error) => setError(reason.message))
  }, [])
  const kpis = summary?.kpis
  return <SafeAreaView style={styles.safe}><StatusBar style="dark" /><ScrollView contentContainerStyle={styles.content}>
    <Text style={styles.eyebrow}>ADP MOBILE</Text><Text style={styles.title}>今日工作台</Text>
    <Text style={styles.date}>{summary?.date_label ?? '正在连接服务…'}</Text>
    {error ? <Text style={styles.error}>暂时无法加载：{error}</Text> : <View style={styles.grid}>
      {[["塘口总数", kpis?.ponds], ["养殖中批次", kpis?.active_batches], ["当前存量", kpis?.current_stock], ["我的待办", kpis?.todo_open]].map(([label, value]) => <View key={String(label)} style={styles.card}><Text style={styles.label}>{label}</Text><Text style={styles.value}>{value ?? '—'}</Text></View>)}
    </View>}
  </ScrollView></SafeAreaView>
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f5faf8' }, content: { padding: 24, gap: 8 },
  eyebrow: { color: '#2c6b65', fontSize: 12, fontWeight: '700', letterSpacing: 1.5 }, title: { color: '#243148', fontSize: 32, fontWeight: '700', marginTop: 4 }, date: { color: '#6c7b82', fontSize: 14, marginBottom: 20 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 }, card: { width: '47%', minHeight: 110, padding: 16, borderRadius: 10, backgroundColor: '#fff', borderWidth: 1, borderColor: '#dbe9e5' }, label: { color: '#6c7b82', fontSize: 13 }, value: { color: '#1f776d', fontSize: 28, fontWeight: '700', marginTop: 16 }, error: { color: '#9d3b43', backgroundColor: '#fff0f0', padding: 14, borderRadius: 8 }
})
