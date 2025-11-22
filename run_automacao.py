import tkinter as tk
from tkinter import ttk, messagebox
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env ANTES de qualquer outra coisa.
load_dotenv()

import automacao_servopa_corrigidoen
import threading
import sys
import os
import sv_ttk # Importa o novo tema

class TextRedirector:
    def __init__(self, widget):
        self.widget = widget

    def write(self, st):
        self.widget.config(state=tk.NORMAL)
        self.widget.insert(tk.END, st)
        self.widget.see(tk.END)
        self.widget.config(state=tk.DISABLED)

    def flush(self):
        pass

class ThreadWithReturnValue(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        threading.Thread.__init__(self, group, target, name, args, kwargs)
        self._return = None

    def run(self):
        if self._target is not None:
            self._return = self._target(*self._args, **self._kwargs)

    def join(self, *args):
        threading.Thread.join(self, *args)
        return self._return

class AutomationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Painel de Automação Servopa v5.0")
        self.root.geometry("850x750")

        self.active_thread = None
        self.stop_flag = threading.Event()
        self.cota_count_timer = None

        self.placeholder_text = "Selecione ou digite um novo consultor..."
        self.placeholder_color = 'grey'
        self.default_fg_color = self.root.option_get('foreground', '.')

        self.consultores_list = self.get_consultores()
        self.create_widgets()
        self.redirect_output()

    def get_consultores(self):
        lances_dir = os.path.abspath("Lances")
        if not os.path.exists(lances_dir):
            os.makedirs(lances_dir)
            return []
        try:
            return sorted([d for d in os.listdir(lances_dir) if os.path.isdir(os.path.join(lances_dir, d))])
        except OSError as e:
            messagebox.showerror("Erro de Diretório", f"Não foi possível ler o diretório de Lances: {e}")
            return []

    def create_widgets(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(expand=True, fill='both', padx=5, pady=5)

        tab_automacao = ttk.Frame(notebook, padding="10")
        tab_logs = ttk.Frame(notebook, padding="10")

        notebook.add(tab_automacao, text='Automação')
        notebook.add(tab_logs, text='Visualizador de Logs')

        self.setup_automation_tab(tab_automacao)
        self.setup_log_viewer_tab(tab_logs)

        self.root.bind("<Return>", self.start_automation_on_enter)

    def setup_automation_tab(self, parent_tab):
        parent_tab.grid_columnconfigure(0, weight=1)
        parent_tab.grid_rowconfigure(1, weight=1)
        parent_tab.grid_rowconfigure(4, weight=1)

        input_frame = ttk.LabelFrame(parent_tab, text="1. Configurações", padding="10")
        input_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        input_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="Consultor:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.entry_consultor = ttk.Combobox(input_frame, width=40, values=self.consultores_list)
        self.entry_consultor.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.entry_consultor.focus_set()
        self.set_placeholder()
        self.entry_consultor.bind("<FocusIn>", self.on_focus_in)
        self.entry_consultor.bind("<FocusOut>", self.on_focus_out)

        lances_frame = ttk.LabelFrame(parent_tab, text="2. Lista de Cotas", padding="10")
        lances_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        lances_frame.grid_columnconfigure(0, weight=1)
        lances_frame.grid_rowconfigure(0, weight=1)

        self.lances_text = tk.Text(lances_frame, height=10, width=60, wrap=tk.WORD)
        self.lances_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(lances_frame, command=self.lances_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.lances_text.config(yscrollcommand=scrollbar.set)
        self.lances_text.bind("<KeyRelease>", self.update_cota_count)

        self.cota_count_label = ttk.Label(parent_tab, text="Total de Cotas Válidas: 0", style="Italic.TLabel")
        self.cota_count_label.grid(row=2, column=0, sticky="e", padx=15, pady=(0,10))

        control_frame = ttk.LabelFrame(parent_tab, text="3. Ações", padding="10")
        control_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        control_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_start = ttk.Button(control_frame, text="Iniciar Automação de Lances", command=self.start_automation_threaded, style="Accent.TButton")
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        self.btn_verify = ttk.Button(control_frame, text="Verificar Nomes na Pasta", command=self.start_verification_threaded)
        self.btn_verify.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        self.btn_stop = ttk.Button(control_frame, text="Finalizar Operação", command=self.stop_operation, state=tk.DISABLED)
        self.btn_stop.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        log_frame = ttk.LabelFrame(parent_tab, text="4. Logs da Operação Atual", padding="10")
        log_frame.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=10, state=tk.DISABLED)
        log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.grid(row=0, column=1, sticky="ns")

    def setup_log_viewer_tab(self, parent_tab):
        parent_tab.grid_columnconfigure(0, weight=1)
        parent_tab.grid_rowconfigure(1, weight=1)

        viewer_control_frame = ttk.LabelFrame(parent_tab, text="Controles do Visualizador", padding="10")
        viewer_control_frame.grid(row=0, column=0, sticky="ew")
        viewer_control_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(viewer_control_frame, text="Arquivo de Log:").grid(row=0, column=0, padx=(0, 5), pady=5, sticky="w")
        self.log_file_selector = ttk.Combobox(viewer_control_frame, values=["automacao.log", "erros_lances_2.txt"], state="readonly")
        self.log_file_selector.grid(row=0, column=1, columnspan=2, sticky="ew", padx=5, pady=5)
        self.log_file_selector.set("automacao.log")
        self.log_file_selector.bind("<<ComboboxSelected>>", self.on_log_file_change)

        ttk.Label(viewer_control_frame, text="Destacar termo:").grid(row=1, column=0, padx=(0, 5), pady=5, sticky="w")
        self.log_filter_entry = ttk.Entry(viewer_control_frame)
        self.log_filter_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5, pady=5)
        self.log_filter_entry.bind("<Return>", self.on_search_enter)
        self.log_filter_entry.bind("<KeyRelease>", self.on_filter_key_release)

        button_frame = ttk.Frame(viewer_control_frame)
        button_frame.grid(row=2, column=0, columnspan=3, sticky="e")
        self.match_count_label = ttk.Label(button_frame, text="")
        self.match_count_label.pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Button(button_frame, text="Ir para o Final", command=self.scroll_log_viewer_to_end).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(button_frame, text="Carregar / Buscar", command=self.on_search_enter, style="Accent.TButton").pack(side=tk.LEFT, padx=5, pady=5)
        
        self.btn_edit_log = ttk.Button(button_frame, text="Habilitar Edição", command=self.toggle_log_edit_mode)
        self.btn_edit_log.pack(side=tk.LEFT, padx=5, pady=5)
        self.btn_save_log = ttk.Button(button_frame, text="Salvar Alterações", command=self.save_log_changes, state=tk.DISABLED)
        self.btn_save_log.pack(side=tk.LEFT, padx=5, pady=5)

        log_display_frame = ttk.LabelFrame(parent_tab, text="Conteúdo do Log", padding="10")
        log_display_frame.grid(row=1, column=0, sticky="nsew", pady=(10,0))
        log_display_frame.grid_columnconfigure(0, weight=1)
        log_display_frame.grid_rowconfigure(0, weight=1)

        self.log_viewer_text = tk.Text(log_display_frame, wrap=tk.WORD, height=10, state=tk.DISABLED)
        log_viewer_scrollbar = ttk.Scrollbar(log_display_frame, command=self.log_viewer_text.yview)
        self.log_viewer_text.config(yscrollcommand=log_viewer_scrollbar.set)
        self.log_viewer_text.grid(row=0, column=0, sticky="nsew")
        log_viewer_scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_viewer_text.tag_configure("highlight", background="#003366")
        self.log_viewer_text.tag_configure("current_match", background="#0055AA", borderwidth=1, relief="solid")

    def on_log_file_change(self, event=None):
        self.log_filter_entry.delete(0, tk.END)
        self.load_selected_log()

    def load_selected_log(self):
        if self.log_viewer_text.cget("state") == tk.NORMAL:
            self.toggle_log_edit_mode()

        log_file = self.log_file_selector.get()
        if not log_file:
            return

        self.log_viewer_text.config(state=tk.NORMAL)
        self.log_viewer_text.delete("1.0", tk.END)

        try:
            log_path = os.path.abspath(log_file)
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.log_viewer_text.insert(tk.END, content)
        except FileNotFoundError:
            self.log_viewer_text.insert(tk.END, f"Arquivo '{log_file}' ainda não foi criado.")
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível ler o arquivo de log: {e}")
        finally:
            self.log_viewer_text.config(state=tk.DISABLED)
        
        self.on_search_enter()

    def on_search_enter(self, event=None):
        term = self.log_filter_entry.get().strip()
        if not term:
            self.clear_log_viewer_highlights()
            return

        if term.lower() == getattr(self, 'last_search_term', '').lower():
            self._find_next_match()
        else:
            self._perform_new_search(term)

    def _perform_new_search(self, term):
        self.last_search_term = term
        self.search_matches = []
        self.current_match_index = -1

        self.log_viewer_text.config(state=tk.NORMAL)
        self.log_viewer_text.tag_remove("highlight", "1.0", tk.END)
        self.log_viewer_text.tag_remove("current_match", "1.0", tk.END)

        start_pos = "1.0"
        while True:
            start_pos = self.log_viewer_text.search(term, start_pos, stopindex=tk.END, nocase=True)
            if not start_pos:
                break
            end_pos = f"{start_pos}+{len(term)}c"
            self.search_matches.append(start_pos)
            self.log_viewer_text.tag_add("highlight", start_pos, end_pos)
            start_pos = end_pos
        
        self.log_viewer_text.config(state=tk.DISABLED)
        self.match_count_label.config(text=f"Encontrados: {len(self.search_matches)}")
        self._find_next_match()

    def _find_next_match(self):
        if not self.search_matches:
            return

        self.log_viewer_text.tag_remove("current_match", "1.0", tk.END)

        self.current_match_index = (self.current_match_index + 1) % len(self.search_matches)

        start_pos = self.search_matches[self.current_match_index]
        self.log_viewer_text.tag_add("current_match", start_pos, f"{start_pos}+{len(self.last_search_term)}c")
        self.log_viewer_text.see(start_pos)

    def on_filter_key_release(self, event=None):
        if not self.log_filter_entry.get().strip():
            self.clear_log_viewer_highlights()

    def clear_log_viewer_highlights(self):
        self.log_viewer_text.tag_remove("highlight", "1.0", tk.END)
        self.log_viewer_text.tag_remove("current_match", "1.0", tk.END)
        self.match_count_label.config(text="")
        self.last_search_term = ""
        self.search_matches = []
        self.current_match_index = -1

    def toggle_log_edit_mode(self):
        current_state = self.log_viewer_text.cget("state")
        if current_state == tk.DISABLED:
            self.log_viewer_text.config(state=tk.NORMAL)
            self.btn_edit_log.config(text="Desabilitar Edição")
            self.btn_save_log.config(state=tk.NORMAL)
        else:
            self.log_viewer_text.config(state=tk.DISABLED)
            self.btn_edit_log.config(text="Habilitar Edição")
            self.btn_save_log.config(state=tk.DISABLED)

    def save_log_changes(self):
        log_file = self.log_file_selector.get()
        if not log_file:
            messagebox.showwarning("Aviso", "Nenhum arquivo de log selecionado.")
            return

        if messagebox.askyesno("Confirmar", f"Tem certeza que deseja sobrescrever o arquivo '{log_file}' com o conteúdo atual?"):
            try:
                content = self.log_viewer_text.get("1.0", tk.END)
                log_path = os.path.abspath(log_file)
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("Sucesso", f"Arquivo '{log_file}' salvo com sucesso.")
                self.toggle_log_edit_mode()
            except Exception as e:
                messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o arquivo: {e}")

    def scroll_log_viewer_to_end(self):
        self.log_viewer_text.see(tk.END)

    def set_placeholder(self):
        if not self.entry_consultor.get():
            self.entry_consultor.insert(0, self.placeholder_text)
            self.entry_consultor.config(foreground=self.placeholder_color)

    def on_focus_in(self, event):
        if self.entry_consultor.get() == self.placeholder_text:
            self.entry_consultor.delete(0, tk.END)
            self.entry_consultor.config(foreground=self.default_fg_color)

    def on_focus_out(self, event):
        if not self.entry_consultor.get():
            self.set_placeholder()

    def redirect_output(self):
        sys.stdout = TextRedirector(self.log_text)
        sys.stderr = TextRedirector(self.log_text)
        automacao_servopa_corrigido.setup_logging()

    def start_automation_on_enter(self, event=None):
        if self.btn_start['state'] == tk.NORMAL:
            self.start_automation_threaded()

    def update_cota_count(self, event=None):
        if self.cota_count_timer:
            self.root.after_cancel(self.cota_count_timer)
        self.cota_count_timer = self.root.after(300, self._perform_cota_count)

    def _perform_cota_count(self):
        content = self.lances_text.get("1.0", tk.END)
        valid_cotas, _ = automacao_servopa_corrigido.parse_lances_from_string(content)
        count = len(valid_cotas)
        self.cota_count_label.config(text=f"Total de Cotas Válidas: {count}")

    def _check_thread_completion(self, formatter_func, title):
        """Função genérica para monitorar threads, formatar o resultado e exibir o popup final."""
        if self.active_thread and self.active_thread.is_alive():
            self.root.after(100, self._check_thread_completion, formatter_func, title)
        else:
            report_data = self.active_thread.join()
            
            if formatter_func:
                formatter_func(report_data)
            
            self.set_ui_state(tk.NORMAL)

            # Lógica centralizada para o messagebox final
            if not report_data:
                messagebox.showerror(f"{title} - Erro", "A operação falhou em produzir um relatório.")
                return

            final_message = ""
            # Mensagem para verificação de nomes
            if title == "Verificação de Nomes":
                total = report_data.get('total_scanned', 0)
                renamed = report_data.get('renamed', 0)
                conflicts = report_data.get('conflicts', 0)
                errors = report_data.get('errors', 0)
                
                if total > 0 and renamed == 0 and conflicts == 0 and errors == 0:
                    final_message = "Perfeito! Todos os nomes de arquivos já estavam corretos."
                elif renamed > 0 and conflicts == 0 and errors == 0:
                    final_message = f"Ótimo! {renamed} arquivo(s) foram corrigidos com sucesso."
                elif conflicts > 0 or errors > 0:
                    final_message = "Atenção: A verificação terminou, mas encontrou conflitos ou erros."
                else:
                    final_message = "Operação concluída. Nenhum arquivo precisou de correção."
                
                if conflicts > 0 or errors > 0:
                    messagebox.showwarning(f"{title} - Concluído com Atenção", final_message)
                else:
                    messagebox.showinfo(f"{title} - Concluído", final_message)

            # Mensagem para automação de lances
            elif title == "Automação de Lances":
                sucesso = report_data.get('sucesso', 0)
                critico = report_data.get('critico', 0)
                final_message = f"Automação finalizada!\n\nLances com Sucesso: {sucesso}\nErros Críticos: {critico}"
                if critico > 0:
                    messagebox.showwarning(f"{title} - Concluído com Atenção", final_message)
                else:
                    messagebox.showinfo(f"{title} - Concluído", final_message)

    def stop_operation(self):
        if self.active_thread and self.active_thread.is_alive():
            print("\n--- SINAL DE PARADA ENVIADO ---\nA operação será encerrada em breve.\n")
            self.stop_flag.set()
            self.btn_stop.config(state=tk.DISABLED)

    def start_automation_threaded(self):
        if self.active_thread and self.active_thread.is_alive():
            messagebox.showwarning("Aviso", "Uma operação já está em andamento.")
            return

        consultor_name = self.entry_consultor.get().strip()
        if not consultor_name or consultor_name == self.placeholder_text:
            messagebox.showwarning("Aviso", "Por favor, insira ou selecione o nome do consultor.")
            return

        lances_text_content = self.lances_text.get("1.0", tk.END).strip()
        if not lances_text_content:
            messagebox.showwarning("Aviso", "Por favor, cole a lista de cotas na caixa de texto.")
            return

        self.stop_flag.clear()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, f"Iniciando automação para o consultor: {consultor_name}...\n")
        self.log_text.config(state=tk.DISABLED)

        self.set_ui_state(tk.DISABLED)
        
        self.active_thread = ThreadWithReturnValue(
            target=automacao_servopa_corrigido.main, 
            args=(consultor_name, lances_text_content, self.stop_flag)
        )
        self.active_thread.start()
        
        self._check_thread_completion(self.format_automation_summary, "Automação de Lances")

    def start_verification_threaded(self):
        if self.active_thread and self.active_thread.is_alive():
            messagebox.showwarning("Aviso", "Uma operação já está em andamento.")
            return

        consultor_name = self.entry_consultor.get().strip()
        if not consultor_name or consultor_name == self.placeholder_text:
            messagebox.showwarning("Aviso", "Por favor, selecione um consultor para verificar a pasta.")
            return

        self.stop_flag.clear()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, f"Iniciando verificação de nomes para o consultor: {consultor_name}...\n")
        self.log_text.config(state=tk.DISABLED)

        self.set_ui_state(tk.DISABLED)
        
        self.active_thread = ThreadWithReturnValue(
            target=automacao_servopa_corrigido.executar_verificacao_nomes, 
            args=(consultor_name,)
        )
        self.active_thread.start()
        
        self._check_thread_completion(self.format_verification_summary, "Verificação de Nomes")

    def set_ui_state(self, state):
        self.btn_start.config(state=state)
        self.btn_verify.config(state=state)
        self.btn_stop.config(state=tk.NORMAL if state == tk.DISABLED else tk.DISABLED)
        self.entry_consultor.config(state='normal' if state == tk.NORMAL else 'disabled')
        self.lances_text.config(state=tk.NORMAL if state == tk.NORMAL else tk.DISABLED)

    def format_verification_summary(self, report):
        """Formata e imprime o relatório da verificação de nomes."""
        print("\n" + "="*60)
        print("     🔎 RELATÓRIO FINAL DA VERIFICAÇÃO DE NOMES 🔎")
        print("="*60 + "\n")

        if not report:
            print("❌ A verificação não foi executada ou falhou ao iniciar.")
            print("="*60)
            return

        print("📋 Resumo da Verificação:")
        print("------------------------------------------------------------")
        print(f"  - 📂 Arquivos Escaneados: {report.get('total_scanned', 0)}")
        print(f"  - ✅ Nomes Corretos: {report.get('correct', 0)}")
        print(f"  - ✏️ Arquivos Renomeados: {report.get('renamed', 0)}")
        print(f"  - ⚠️ Conflitos Encontrados: {report.get('conflicts', 0)}")
        print(f"  - ❌ Erros de Leitura: {report.get('errors', 0)}")
        print("------------------------------------------------------------\n")

    def format_automation_summary(self, summary):
        """Formata e imprime o relatório da automação de lances no log."""
        print("\n" + "="*60)
        print("     📊 RELATÓRIO FINAL DA AUTOMAÇÃO DE LANCES 📊")
        print("="*60 + "\n")

        if not summary:
            print("❌ A automação não foi executada ou falhou ao iniciar.")
            print("="*60)
            return

        print("📋 Resumo dos Lances:")
        print("------------------------------------------------------------")
        print(f"  - ➡️  Cotas Recebidas: {summary.get('total_cotas', 0)}")
        print(f"  - ⏭️  Cotas Puladas (já existentes): {summary.get('cotas_puladas', 0)}")
        print(f"  - ⚙️  Cotas a Processar: {summary.get('cotas_a_processar', 0)}")
        print("\n------------------------------------------------------------")
        print(f"  - ✅ Lances com Sucesso: {summary.get('sucesso', 0)}")
        print(f"  - ℹ️  Cotas com Status Benigno: {summary.get('benigno', 0)}")
        print(f"  - ❌ Cotas com Erro Crítico: {summary.get('critico', 0)}")
        print("------------------------------------------------------------\n")

        total = summary.get('cotas_a_processar', 0)
        sucesso = summary.get('sucesso', 0)
        critico = summary.get('critico', 0)

        if critico == 0 and sucesso > 0:
            print("🎉 Perfeito! Todos os lances foram registrados com sucesso.")
        elif sucesso > critico:
            print("👍 Ótimo trabalho! A maioria dos lances foi registrada corretamente.")
        elif critico > 0:
            print("⚠️ Atenção: A automação terminou, mas uma parte dos lances encontrou erros críticos.")
        else:
            print("ℹ️ Operação concluída. Verifique os logs para mais detalhes.")
        
        print("="*60)

if __name__ == "__main__":
    root = tk.Tk()
    sv_ttk.set_theme("dark")
    style = ttk.Style()
    style.configure("Italic.TLabel", font=("Helvetica", 9, "italic"))
    style.configure("Accent.TButton", font=("Helvetica", 10, "bold"))
    style.configure("TLabelFrame.Label", font=("Helvetica", 12, "bold"))

    app = AutomationApp(root)
    root.mainloop()