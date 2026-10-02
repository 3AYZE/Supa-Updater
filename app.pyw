"""SupaUpdater Windows desktop UI. No installation occurs without confirmation."""
import queue
import os
import sys
import subprocess
from pathlib import Path
import self_update
import threading
import time
from datetime import datetime, timezone
from storage import load_settings, save_settings, record_result, read_history, HISTORY
import tkinter as tk
from tkinter import ttk, messagebox
from engine import inventory, update_one, uninstall_one, LOG
from driver_scan import scan_drivers
from windows_updates import find_driver_updates, install_driver_update

BG='#f3f5f9'; WHITE='#ffffff'; TEXT='#182438'; MUTED='#657287'; BLUE='#1769cf'; BORDER='#dce3ec'
PALETTES={'Light':('#f3f5f9','#ffffff','#182438','#657287','#1769cf','#dce3ec','#e9eef6'),'Dark':('#161a22','#242a35','#f2f5fa','#aab5c5','#62a2ff','#414b5b','#202632')}

class SupaUpdater(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SupaUpdater')
        self.geometry('1120x740'); self.minsize(860,580)
        self.configure(bg=BG)
        self._apply_app_icon()
        self.events=queue.Queue(); self.updates={}; self.registry=[]; self.drivers=[]; self.driver_scanning=False; self.driver_offers=[]; self.driver_selected=set(); self.driver_busy=False
        self.theme_choice=tk.StringVar(value=load_settings().get('theme','System'))
        self.busy=False; self.self_busy=False; self.stop=False; self.filter=tk.StringVar(value='All updates')
        self.query=tk.StringVar(); self.query.trace_add('write',lambda *_:self.refresh())
        self.selected=set(); self.page='Updates'
        self.queue_started=None; self.current_started=None; self.completed_durations=[]; self.queue_total=0; self.queue_completed=0; self.queue_failed=0; self.queue_active=False; self.queue_results=[]; self.refreshing_after_update=False
        s=ttk.Style(self); s.theme_use('clam')
        s.configure('Apps.Treeview',background=WHITE,fieldbackground=WHITE,foreground=TEXT,rowheight=38,borderwidth=0,font=('Segoe UI',10))
        s.configure('Apps.Treeview.Heading',background='#eaf0f8',foreground=TEXT,font=('Segoe UI',10,'bold'),padding=(10,11),relief='flat')
        s.map('Apps.Treeview',background=[('selected','#dceafd')],foreground=[('selected',TEXT)])
        s.configure('TScrollbar',background='#cbd5e1')
        self.sidebar=tk.Frame(self,bg='#e9eef6',width=210);self.sidebar.pack(side='left',fill='y');self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar,text='SupaUpdater',font=('Segoe UI',19,'bold'),bg='#e9eef6',fg=TEXT).pack(anchor='w',padx=19,pady=(26,5))
        tk.Label(self.sidebar,text='SOFTWARE & DRIVER UPDATES',font=('Segoe UI',8,'bold'),bg='#e9eef6',fg=MUTED).pack(anchor='w',padx=21,pady=(0,28))
        self.nav={}
        for label in ('Updates','Activity','Settings'):
            b=tk.Button(self.sidebar,text='   '+label,anchor='w',font=('Segoe UI',11),relief='flat',bd=0,padx=16,pady=13,command=lambda x=label:self.show_page(x))
            b.pack(fill='x',padx=10,pady=3);self.nav[label]=b
        tk.Label(self.sidebar,text='Free • Local software updater',bg='#e9eef6',fg=MUTED,font=('Segoe UI',9),wraplength=175).pack(side='bottom',pady=22)
        self.main=tk.Frame(self,bg=BG);self.main.pack(side='left',fill='both',expand=True,padx=28,pady=24)
        top=tk.Frame(self.main,bg=BG);top.pack(fill='x')
        self.heading=tk.Label(top,text='Available updates',font=('Segoe UI',23,'bold'),bg=BG,fg=TEXT);self.heading.pack(side='left')
        self.scanbtn=tk.Button(top,text='Scan software',command=self.scan,bg=BLUE,fg='white',activebackground='#1359b2',activeforeground='white',relief='flat',font=('Segoe UI',10,'bold'),padx=17,pady=10,cursor='hand2');self.scanbtn.pack(side='right')
        self.selfupdatebtn=tk.Button(top,text='Driver updates',command=lambda:self.show_page('Driver updates'),bg=WHITE,fg=BLUE,relief='solid',bd=1,font=('Segoe UI',10,'bold'),padx=12,pady=10,cursor='hand2');self.selfupdatebtn.pack(side='right',padx=(0,10))
        self.subtitle=tk.Label(self.main,text='Select the updates you want, then install them.',font=('Segoe UI',10),bg=BG,fg=MUTED);self.subtitle.pack(anchor='w',pady=(2,17))
        self.stats=tk.Label(self.main,text='Run a scan to find available updates.',font=('Segoe UI',10,'bold'),bg=BG,fg=TEXT);self.stats.pack(anchor='w',pady=(0,15))
        toolbar=tk.Frame(self.main,bg=BG);toolbar.pack(fill='x',pady=(0,12))
        self.search=tk.Entry(toolbar,textvariable=self.query,font=('Segoe UI',11),bg=WHITE,fg=TEXT,relief='solid',bd=1,highlightthickness=0)
        self.search.pack(side='left',fill='x',expand=True,ipady=8)
        self.filterbox=ttk.Combobox(toolbar,textvariable=self.filter,values=('All updates','Selected only'),state='readonly',width=17,font=('Segoe UI',10))
        self.filterbox.pack(side='left',padx=(10,0),ipady=6);self.filterbox.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        selection=tk.Frame(self.main,bg=BG);selection.pack(fill='x',pady=(0,10))
        self.allbtn=tk.Button(selection,text='☐  Select all visible',command=self.select_all,bg=WHITE,fg=TEXT,relief='solid',bd=1,padx=12,pady=7,font=('Segoe UI',10));self.allbtn.pack(side='left')
        self.clearbtn=tk.Button(selection,text='Clear selection',command=self.clear_selection,bg=BG,fg=BLUE,relief='flat',padx=13,pady=7,font=('Segoe UI',10));self.clearbtn.pack(side='left')
        self.selected_label=tk.Label(selection,text='0 selected',bg=BG,fg=MUTED,font=('Segoe UI',10));self.selected_label.pack(side='right')
        container=tk.Frame(self.main,bg=WHITE,highlightbackground=BORDER,highlightthickness=1);container.pack(fill='both',expand=True)
        self.table=ttk.Treeview(container,columns=('check','name','installed','available','source'),show='headings',selectmode='none',style='Apps.Treeview')
        for key,title,width,stretch in [('check','Select',62,False),('name','Application',250,True),('installed','Installed',115,False),('available','Available',115,False),('source','Source',115,False)]:
            self.table.heading(key,text=title);self.table.column(key,width=width,minwidth=width if not stretch else 160,stretch=stretch,anchor='center' if key=='check' else 'w')
        y=ttk.Scrollbar(container,orient='vertical',command=self.table.yview);self.table.configure(yscrollcommand=y.set)
        self.table.pack(side='left',fill='both',expand=True);y.pack(side='right',fill='y')
        self.table.bind('<Button-1>',self.click_row)
        bottom=tk.Frame(self.main,bg=BG);bottom.pack(fill='x',pady=(10,12),before=container)
        self.uninstallbtn=tk.Button(bottom,text='Uninstall selected',command=self.uninstall_selected,bg=WHITE,fg='#b42318',relief='solid',bd=1,font=('Segoe UI',10,'bold'),padx=15,pady=10,state='disabled');self.uninstallbtn.pack(side='left')
        self.updatebtn=tk.Button(bottom,text='Install selected (0)',command=self.update_selected,bg=BLUE,fg=WHITE,relief='flat',font=('Segoe UI',10,'bold'),padx=19,pady=11,state='disabled');self.updatebtn.pack(side='right')
        self.updateallbtn=tk.Button(bottom,text='Install all available',command=self.update_all,bg='#176e47',fg=WHITE,relief='flat',font=('Segoe UI',10,'bold'),padx=17,pady=11,state='disabled');self.updateallbtn.pack(side='right',padx=(0,9))
        self.cancelbtn=tk.Button(bottom,text='Stop after current update',command=self.cancel,bg=WHITE,fg=TEXT,relief='solid',bd=1,padx=14,pady=10,state='disabled');self.cancelbtn.pack(side='right',padx=9)
        progress=tk.Frame(self.main,bg=WHITE,highlightbackground=BORDER,highlightthickness=1)
        progress.pack(fill='x',pady=(10,12),ipadx=12,ipady=9, before=container)
        self.progress_title=tk.StringVar(value='No update in progress')
        tk.Label(progress,textvariable=self.progress_title,font=('Segoe UI',10,'bold'),bg=WHITE,fg=TEXT,anchor='w').pack(fill='x',padx=12,pady=(2,5))
        self.progressbar=ttk.Progressbar(progress,orient='horizontal',mode='determinate',maximum=100)
        self.progressbar.pack(fill='x',padx=12)
        self.progress_detail=tk.StringVar(value='Select applications and choose Update selected.')
        tk.Label(progress,textvariable=self.progress_detail,font=('Segoe UI',9),bg=WHITE,fg=MUTED,anchor='w').pack(fill='x',padx=12,pady=(5,1))
        self.results_frame=tk.Frame(self.main,bg=WHITE,highlightbackground=BORDER,highlightthickness=1)
        self.results_title=tk.StringVar(value='')
        tk.Label(self.results_frame,textvariable=self.results_title,font=('Segoe UI',10,'bold'),bg=WHITE,fg=TEXT).pack(anchor='w',padx=12,pady=(8,2))
        self.results_text=tk.Text(self.results_frame,height=5,wrap='word',state='disabled',bg=WHITE,fg=TEXT,relief='flat',font=('Segoe UI',9))
        self.results_text.pack(fill='x',padx=12,pady=(0,8))
        self.status=tk.StringVar(value='Ready. No software has been modified.')
        tk.Label(self.main,textvariable=self.status,font=('Segoe UI',9),bg=BG,fg=MUTED,anchor='w',wraplength=850,justify='left').pack(fill='x',pady=(13,0))
        self.app_update_frame=tk.Frame(self.main,bg=BG)
        self.app_update_progress=tk.DoubleVar(value=0)
        self.app_update_detail=tk.StringVar(value='No app download in progress')
        self.app_update_status=tk.StringVar(value='Check the official GitHub repository for a newer SupaUpdater version.')
        settings=load_settings()
        self.repo=tk.StringVar(value=settings.get('repository') or self_update.DEFAULT_REPO)
        self.auto_check=tk.BooleanVar(value=bool(settings.get('auto_check',True)))
        self.release=None
        self.show_page('Updates');self.apply_theme();self.after(100,self.poll);self.after(2500,self.check_theme)
        if self.auto_check.get() and self.repo.get():self.after(1500,self.check_app_update)

    def show_page(self,page):
        self.page=page
        for name,button in self.nav.items():button.config(bg='#d5e6fc' if name==page else '#e9eef6',fg=BLUE if name==page else TEXT)
        self.heading.config(text={'Updates':'Available updates','Installed apps':'Installed applications','Activity':'Activity & diagnostics','App updates':'SupaUpdater updates','Driver updates':'Driver updates','Settings':'Settings'}[page])
        self.subtitle.config(text={'Updates':'Choose which applications to update.','Installed apps':'Inventory from the Windows registry. Only verified updates are installable.','Activity':f'Log file: {LOG}','App updates':'Check for new versions of SupaUpdater itself.','Driver updates':'Discover and install selected Windows Update driver packages. Firmware requires vendor tools.','Settings':'Choose appearance and update preferences.'}[page])
        if page in ('App updates','Activity','Driver updates','Settings'):self.scanbtn.pack_forget()
        elif not self.scanbtn.winfo_manager():self.scanbtn.pack(side='right')
        is_update=page=='Updates'
        self.filterbox.config(state='readonly' if is_update else 'disabled')
        self.allbtn.config(state='normal' if is_update and not self.busy and not self.self_busy else 'disabled')
        self.clearbtn.config(state='normal' if is_update and not self.busy and not self.self_busy else 'disabled')
        sections=(self.stats,self.search.master,self.allbtn.master,self.table.master,self.updatebtn.master,self.progressbar.master)
        if page in ('App updates','Activity','Driver updates','Settings'):
            self.app_update_frame.pack_forget()
            if hasattr(self,'activity_frame'):self.activity_frame.pack_forget()
            if hasattr(self,'driver_frame'):self.driver_frame.pack_forget()
            if hasattr(self,'settings_frame'):self.settings_frame.pack_forget()
            for widget in sections:
                if widget.winfo_manager():
                    widget._saved_pack=widget.pack_info()
                    widget.pack_forget()
            if page=='App updates': self.show_app_updates()
            elif page=='Activity':self.show_activity()
            elif page=='Driver updates':self.show_drivers()
            else:self.show_settings()
        else:
            self.app_update_frame.pack_forget()
            if hasattr(self,'activity_frame'):self.activity_frame.pack_forget()
            if hasattr(self,'driver_frame'):self.driver_frame.pack_forget()
            if hasattr(self,'settings_frame'):self.settings_frame.pack_forget()
            for widget in sections:
                if not widget.winfo_manager() and hasattr(widget,'_saved_pack'):
                    widget.pack(**widget._saved_pack)
        self.refresh()
        self.show_nav_colors()

    def system_theme(self):
        if sys.platform!='win32':return 'Light'
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                value,_=winreg.QueryValueEx(key,'AppsUseLightTheme')
                return 'Light' if value else 'Dark'
        except OSError:return 'Light'

    def apply_theme(self):
        global BG,WHITE,TEXT,MUTED,BLUE,BORDER
        mode=self.theme_choice.get(); actual=self.system_theme() if mode=='System' else mode
        BG,WHITE,TEXT,MUTED,BLUE,BORDER,side=PALETTES[actual]
        self.configure(bg=BG)
        style=ttk.Style(self)
        style.configure('Apps.Treeview',background=WHITE,fieldbackground=WHITE,foreground=TEXT)
        style.configure('Apps.Treeview.Heading',background=side,foreground=TEXT)
        style.map('Apps.Treeview',background=[('selected','#35567d' if actual=='Dark' else '#dceafd')],foreground=[('selected',TEXT)])
        style.configure('TCombobox',fieldbackground=WHITE,background=WHITE,foreground=TEXT)
        style.map('TCombobox',fieldbackground=[('readonly',WHITE)],foreground=[('readonly',TEXT)])
        def recolor(widget):
            if isinstance(widget,(tk.Frame,tk.Label,tk.Button,tk.Entry,tk.Text,tk.Checkbutton)):
                try:
                    old=widget.cget('bg'); target=side if widget is self.sidebar or str(widget).startswith(str(self.sidebar)+'.') else BG
                    if old in ('#e9eef6','#d5e6fc','#202632'):widget.config(bg=side)
                    elif old in ('#f3f5f9','#161a22'):widget.config(bg=BG)
                    elif old in ('#ffffff','#242a35'):widget.config(bg=WHITE)
                    elif old in ('#1769cf','#62a2ff'):widget.config(bg=BLUE)
                    elif old=='#176e47':pass
                    else:widget.config(bg=target)
                    if isinstance(widget,(tk.Label,tk.Button,tk.Entry,tk.Text,tk.Checkbutton)):
                        fg=widget.cget('fg')
                        if fg in ('#657287','#aab5c5'):widget.config(fg=MUTED)
                        elif fg in ('#1769cf','#62a2ff'):widget.config(fg=BLUE)
                        elif fg not in ('white','#FFFFFF'):widget.config(fg=TEXT)
                    if isinstance(widget,tk.Entry):widget.config(insertbackground=TEXT)
                    if isinstance(widget,tk.Text):widget.config(insertbackground=TEXT)
                except tk.TclError:pass
            for child in widget.winfo_children():recolor(child)
        recolor(self)
        self.show_nav_colors()
        if sys.platform=='win32':
            try:
                import ctypes
                enabled=ctypes.c_int(actual=='Dark')
                ctypes.windll.dwmapi.DwmSetWindowAttribute(self.winfo_id(),20,ctypes.byref(enabled),ctypes.sizeof(enabled))
            except (OSError,AttributeError):pass
        self._last_theme=actual

    def show_nav_colors(self):
        side=PALETTES['Dark' if BG=='#161a22' else 'Light'][6]
        for name,button in self.nav.items():button.config(bg=('#334a69' if BG=='#161a22' else '#d5e6fc') if name==self.page else side,fg=BLUE if name==self.page else TEXT)

    def check_theme(self):
        if self.theme_choice.get()=='System' and self.system_theme()!=getattr(self,'_last_theme',None):self.apply_theme()
        self.after(2500,self.check_theme)

    def show_settings(self):
        if not hasattr(self,'settings_frame'):
            self.settings_frame=tk.Frame(self.main,bg=BG)
            tk.Label(self.settings_frame,text='Appearance',font=('Segoe UI',15,'bold'),bg=BG,fg=TEXT).pack(anchor='w',pady=14)
            tk.Label(self.settings_frame,text='Follow Windows automatically, or choose a theme:',bg=BG,fg=MUTED).pack(anchor='w')
            for mode in ('System','Light','Dark'):
                tk.Radiobutton(self.settings_frame,text=mode,variable=self.theme_choice,value=mode,command=lambda:(self.save_preferences(),self.apply_theme()),bg=BG,fg=TEXT,selectcolor=WHITE,activebackground=BG).pack(anchor='w',pady=7)
        self.settings_frame.pack(fill='both',expand=True,after=self.subtitle)
        self.apply_theme()

    def show_drivers(self):
        if not hasattr(self,'driver_frame'):
            self.driver_frame=tk.Frame(self.main,bg=BG)
            bar=tk.Frame(self.driver_frame,bg=BG);bar.pack(fill='x',pady=10)
            self.driver_scan_btn=tk.Button(bar,text='Scan installed drivers',command=self.start_driver_scan,bg=BLUE,fg='white',padx=10,pady=8);self.driver_scan_btn.pack(side='left')
            self.driver_offer_btn=tk.Button(bar,text='Check driver updates',command=self.check_driver_offers,bg=BLUE,fg='white',padx=10,pady=8);self.driver_offer_btn.pack(side='left',padx=8)
            tk.Button(bar,text='Windows optional updates',command=self.open_driver_updates,bg=WHITE,fg=TEXT,padx=10,pady=8).pack(side='left')
            self.driver_note=tk.StringVar(value='Scan for optional drivers. Only Windows Update driver packages can be installed here.')
            tk.Label(self.driver_frame,textvariable=self.driver_note,bg=BG,fg=MUTED,anchor='w',wraplength=730,justify='left').pack(fill='x',pady=8)
            tk.Label(self.driver_frame,text='Available driver updates',font=('Segoe UI',13,'bold'),bg=BG,fg=TEXT).pack(anchor='w')
            actions=tk.Frame(self.driver_frame,bg=BG);actions.pack(fill='x',pady=6)
            tk.Button(actions,text='Select all',command=lambda:self.select_driver_offers(True),bg=WHITE,fg=TEXT).pack(side='left')
            tk.Button(actions,text='Clear selection',command=lambda:self.select_driver_offers(False),bg=WHITE,fg=TEXT).pack(side='left',padx=8)
            self.driver_install_btn=tk.Button(actions,text='Install selected driver updates (0)',command=self.install_selected_drivers,bg='#176e47',fg='white',padx=12,pady=7);self.driver_install_btn.pack(side='right')
            self.driver_offers_table=ttk.Treeview(self.driver_frame,columns=('select','title','size','restart'),show='headings',height=6,style='Apps.Treeview')
            for col,width in [('select',75),('title',410),('size',100),('restart',100)]:
                self.driver_offers_table.heading(col,text=col.title());self.driver_offers_table.column(col,width=width,stretch=col=='title')
            self.driver_offers_table.pack(fill='x',pady=4)
            self.driver_offers_table.bind('<ButtonRelease-1>',self.toggle_driver_offer)
            tk.Label(self.driver_frame,text='Installed hardware drivers',font=('Segoe UI',13,'bold'),bg=BG,fg=TEXT).pack(anchor='w',pady=(12,4))
            table_area=tk.Frame(self.driver_frame,bg=BG);table_area.pack(fill='both',expand=True)
            self.driver_table=ttk.Treeview(table_area,columns=('category','name','version','provider','date'),show='headings',style='Apps.Treeview')
            for col,width in [('category',110),('name',300),('version',125),('provider',150),('date',100)]:
                self.driver_table.heading(col,text=col.title());self.driver_table.column(col,width=width,stretch=col=='name')
            scroll=ttk.Scrollbar(table_area,orient='vertical',command=self.driver_table.yview)
            self.driver_table.configure(yscrollcommand=scroll.set)
            self.driver_table.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.driver_frame.pack(fill='both',expand=True,after=self.subtitle)
        self.driver_table.delete(*self.driver_table.get_children())
        for i,d in enumerate(self.drivers):self.driver_table.insert('','end',iid=str(i),values=(d['category'],d['name'],d['version'],d['provider'],d['date']))
        self.render_driver_offers()
        self.apply_theme()

    def render_driver_offers(self):
        if not hasattr(self,'driver_offers_table'):return
        self.driver_offers_table.delete(*self.driver_offers_table.get_children())
        for i,d in enumerate(self.driver_offers):
            self.driver_offers_table.insert('','end',iid=str(i),values=('☑' if i in self.driver_selected else '☐',d['title'],f"{d['size']/1048576:.1f} MB" if d['size'] else 'Unknown','Yes' if d['reboot'] else 'Possible'))
        self.driver_install_btn.config(text=f'Install selected driver updates ({len(self.driver_selected)})',state='normal' if self.driver_selected and not self.driver_busy and not self.busy and not self.self_busy else 'disabled')
        self.driver_offer_btn.config(state='disabled' if self.driver_busy else 'normal')

    def toggle_driver_offer(self,event):
        if self.driver_busy or self.driver_offers_table.identify_column(event.x)!='#1':return
        row=self.driver_offers_table.identify_row(event.y)
        if not row:return
        i=int(row)
        if i in self.driver_selected:self.driver_selected.remove(i)
        else:self.driver_selected.add(i)
        self.render_driver_offers()

    def select_driver_offers(self,all_items):
        if self.driver_busy:return
        self.driver_selected=set(range(len(self.driver_offers))) if all_items else set()
        self.render_driver_offers()

    def open_driver_updates(self):
        if sys.platform=='win32':os.startfile('ms-settings:windowsupdate-optionalupdates')
        else:messagebox.showinfo('Windows only','Optional driver updates are available in Windows Settings.')

    def start_driver_scan(self):
        if self.driver_scanning or self.driver_busy or self.busy or self.self_busy:return
        self.driver_scanning=True;self.status.set('Scanning installed signed drivers…')
        def work():
            try:self.events.put(('drivers',scan_drivers()))
            except Exception as exc:self.events.put(('driver_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def check_driver_offers(self):
        if self.driver_busy or self.driver_scanning or self.busy or self.self_busy:return
        self.driver_busy=True;self.driver_note.set('Checking Windows Update for optional driver packages…');self.render_driver_offers()
        def work():
            try:self.events.put(('driver_offers',find_driver_updates()))
            except Exception as exc:self.events.put(('driver_offers_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def install_selected_drivers(self):
        if self.driver_busy or self.driver_scanning or self.busy or self.self_busy:return
        chosen=[self.driver_offers[i] for i in sorted(self.driver_selected)]
        if not chosen:return
        summary='\n'.join('• '+d['title'] for d in chosen[:8])
        if not messagebox.askyesno('Confirm driver installation',f'Install {len(chosen)} selected Windows Update driver(s)?\n\n{summary}\n\nSave your work. Hardware may disconnect and Windows may request a restart. Firmware updates are excluded.'):return
        self.driver_busy=True;self.render_driver_offers();self.driver_note.set(f'Installing 0/{len(chosen)} drivers…')
        def work():
            for i,d in enumerate(chosen):
                self.events.put(('driver_install_progress',f"Installing {i+1}/{len(chosen)}: {d['title']} (download/installation percentage unavailable)"))
                try:self.events.put(('driver_install_result',(d,install_driver_update(d),None)))
                except Exception as exc:self.events.put(('driver_install_result',(d,None,str(exc))))
            self.events.put(('driver_install_done',None))
        threading.Thread(target=work,daemon=True).start()

    def show_activity(self):
        if not hasattr(self,'activity_frame'):
            self.activity_frame=tk.Frame(self.main,bg=BG)
            controls=tk.Frame(self.activity_frame,bg=BG);controls.pack(fill='x',pady=8)
            tk.Button(controls,text='Refresh history',command=self.show_activity,bg=WHITE,fg=BLUE).pack(side='left')
            tk.Button(controls,text='Open log folder',command=lambda:os.startfile(str(LOG.parent)) if sys.platform=='win32' else None,bg=WHITE,fg=BLUE).pack(side='left',padx=8)
            self.activity_text=tk.Text(self.activity_frame,wrap='word',bg=WHITE,fg=TEXT,font=('Consolas',10),state='disabled')
            self.activity_text.pack(fill='both',expand=True,pady=8)
        self.activity_frame.pack(fill='both',expand=True,after=self.subtitle)
        self.activity_text.config(state='normal');self.activity_text.delete('1.0','end')
        for r in read_history():
            self.activity_text.insert('end',f"{r.get('time','')} | {r.get('name','')} | {r.get('result','')}\n{r.get('message','')}\n\n")
        self.activity_text.config(state='disabled')

    def save_preferences(self):
        save_settings({'repository':self.repo.get().strip(),'auto_check':self.auto_check.get(),'theme':self.theme_choice.get()})

    def show_app_updates(self):
        self.app_update_frame.pack(fill='both',expand=True,after=self.subtitle)
        for child in self.app_update_frame.winfo_children():child.destroy()
        tk.Label(self.app_update_frame,text=f'Installed version: {self_update.VERSION}',bg=BG,fg=TEXT,font=('Segoe UI',12,'bold')).pack(anchor='w',pady=8)
        tk.Label(self.app_update_frame,text='GitHub repository (owner/repository):',bg=BG,fg=TEXT).pack(anchor='w')
        tk.Entry(self.app_update_frame,textvariable=self.repo,font=('Segoe UI',11),width=40).pack(anchor='w',pady=6)
        tk.Button(self.app_update_frame,text='Save repository settings',command=self.save_preferences,bg=WHITE,fg=BLUE).pack(anchor='w',pady=4)
        tk.Checkbutton(self.app_update_frame,text='Check for updates at startup',variable=self.auto_check,command=self.save_preferences,bg=BG,fg=TEXT).pack(anchor='w')
        tk.Button(self.app_update_frame,text='Check for app updates',command=self.check_app_update,bg=BLUE,fg=WHITE,relief='flat',padx=15,pady=8).pack(anchor='w',pady=8)
        tk.Label(self.app_update_frame,textvariable=self.app_update_status,bg=BG,fg=MUTED,wraplength=650,justify='left').pack(anchor='w',pady=8)
        self.install_app_button=tk.Button(self.app_update_frame,text='Open release to update' if getattr(sys, 'frozen', False) else 'Download and install update',command=self.install_app_update,bg=BLUE,fg=WHITE,relief='flat',padx=15,pady=8,state='normal' if self.release else 'disabled')
        self.install_app_button.pack(anchor='w',pady=8)
        ttk.Progressbar(self.app_update_frame,variable=self.app_update_progress,maximum=100,mode='determinate').pack(fill='x',pady=(6,3))
        tk.Label(self.app_update_frame,textvariable=self.app_update_detail,bg=BG,fg=MUTED).pack(anchor='w',pady=3)

    def check_app_update(self):
        if self.self_busy or self.busy or self.driver_busy or self.driver_scanning:return
        self.self_busy=True
        repo=self.repo.get().strip()
        if not repo:
            self.self_busy=False
            self.app_update_status.set('Enter a valid GitHub repository to check for updates.')
            return
        self.app_update_status.set('Checking GitHub Releases…')
        def work():
            try:self.events.put(('app_check',self_update.check_release(repo)))
            except Exception as exc:self.events.put(('app_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def install_app_update(self):
        if not self.release:return
        if getattr(sys, 'frozen', False):
            import webbrowser
            if messagebox.askyesno('SupaUpdater update', 'The portable EXE cannot replace itself yet. Open the official GitHub release to download the new executable?'):
                webbrowser.open(self.release['release_url'])
            return
        if self.busy or self.self_busy or self.driver_busy or self.driver_scanning:
            messagebox.showwarning('Busy','Finish the current operation before updating SupaUpdater.');return
        if not messagebox.askyesno('Update SupaUpdater',f'Download SupaUpdater {self.release["version"]} and restart the app?\n\nOnly use releases from a repository you trust. Save your work first.'):
            return
        self.self_busy=True
        self.app_update_status.set('Downloading and validating update…')
        self.app_update_progress.set(0)
        self.app_update_detail.set('Starting download…')
        self.install_app_button.config(state='disabled')
        release=self.release
        def work():
            try:self.events.put(('app_staged',self_update.download_and_stage(release,Path(__file__).resolve().parent, progress=lambda received,total:self.events.put(('app_progress',(received,total))))))
            except Exception as exc:self.events.put(('app_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def visible_ids(self):
        q=self.query.get().strip().casefold(); f=self.filter.get()
        return [k for k,a in self.updates.items() if (not q or q in ' '.join((a.name,a.package_id,a.source)).casefold()) and (f!='Selected only' or k in self.selected) and (f!='WinGet' or a.source.casefold()=='winget') and (f!='Other sources' or a.source.casefold()!='winget')]

    def refresh(self):
        self.table.delete(*self.table.get_children())
        if self.page=='Updates':
            ids=self.visible_ids()
            for k in ids:
                a=self.updates[k];self.table.insert('','end',iid=k,values=('☑' if k in self.selected else '☐',a.name,a.installed,a.available,a.source))
            self.stats.config(text=f'{len(self.updates)} available updates  •  {len(ids)} shown')
            self.allbtn.config(text='☑  Deselect visible' if ids and all(k in self.selected for k in ids) else '☐  Select all visible')
        elif self.page=='Installed apps':
            q=self.query.get().strip().casefold();items=[a for a in self.registry if not q or q in (a.name+' '+a.publisher).casefold()]
            for i,a in enumerate(items):self.table.insert('','end',iid=f'reg{i}',values=('',a.name,a.installed,'—',a.publisher))
            self.stats.config(text=f'{len(self.registry)} registry entries  •  {len(items)} shown')
        else:self.stats.config(text='Update progress and errors are recorded in the local log file.')
        self.selected_label.config(text=f'{len(self.selected)} selected')
        self.updatebtn.config(text=f'Update selected ({len(self.selected)})',state='normal' if self.selected and not self.busy and not self.self_busy and self.page=='Updates' else 'disabled')
        self.updateallbtn.config(text=f'Update all available ({len(self.updates)})',state='normal' if self.updates and not self.busy and not self.self_busy and self.page=='Updates' else 'disabled')

    def click_row(self,event):
        if self.busy or self.self_busy or self.page!='Updates':return
        row=self.table.identify_row(event.y)
        if row not in self.updates:return
        if row in self.selected:self.selected.remove(row)
        else:self.selected.add(row)
        self.refresh()

    def select_all(self):
        if self.busy or self.self_busy or self.page!='Updates':return
        ids=set(self.visible_ids())
        if ids and ids.issubset(self.selected):self.selected.difference_update(ids)
        else:self.selected.update(ids)
        self.refresh()

    def clear_selection(self):
        if self.busy or self.self_busy:return
        self.selected.clear();self.refresh()

    def set_busy(self,value):
        self.busy=value;self.scanbtn.config(state='disabled' if value else 'normal');self.cancelbtn.config(state='normal' if value else 'disabled')
        self.allbtn.config(state='disabled' if value or self.page!='Updates' else 'normal');self.clearbtn.config(state='disabled' if value or self.page!='Updates' else 'normal');self.uninstallbtn.config(state='disabled' if value or not self.selected else 'normal');self.refresh()

    def scan(self):
        if self.busy or self.self_busy or self.driver_busy or self.driver_scanning:return
        self.set_busy(True);self.status.set('Scanning registry and WinGet…')
        def work():
            try:self.events.put(('scan',inventory()))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=work,daemon=True).start()

    def uninstall_selected(self):
        if self.busy or self.self_busy or self.driver_busy or self.driver_scanning:return
        apps=[self.updates[k] for k in self.updates if k in self.selected]
        if not apps:
            messagebox.showinfo('Select apps','Select one or more apps from the current list first.');return
        names='\n'.join('• '+a.name for a in apps[:12])
        if len(apps)>12:names+=f'\n…and {len(apps)-12} more'
        if not messagebox.askyesno('Confirm uninstall',f'Uninstall {len(apps)} selected app(s)?\n\n{names}\n\nThis removes the applications, not just their updates. App data may also be removed by each app\'s uninstaller.'):return
        self.set_busy(True);self.queue_total=len(apps);self.queue_completed=0;self.queue_failed=0;self.queue_active=True;self.queue_started=time.monotonic();self.current_started=None;self.queue_results=[]
        self.progressbar.configure(mode='determinate',value=0)
        self.progress_title.set(f'Preparing to uninstall {len(apps)} app(s)')
        def work():
            for a in apps:
                self.events.put(('uninstall_start',a.name))
                try:ok,msg=uninstall_one(a,confirm=True)
                except Exception as exc:ok,msg=False,f'Unexpected uninstall error: {exc}'
                self.events.put(('uninstall_result',(a,ok,msg)))
            self.events.put(('uninstall_done',None))
        threading.Thread(target=work,daemon=True).start()

    def update_selected(self):
        if self.busy or self.self_busy or self.driver_busy or self.driver_scanning:return
        apps=[self.updates[k] for k in self.updates if k in self.selected]
        if not apps:messagebox.showinfo('Select updates','Select one or more verified updates first.');return
        self.start_updates(apps)

    def update_all(self):
        if self.busy or self.self_busy or self.driver_busy or self.driver_scanning or self.page!='Updates':return
        apps=list(self.updates.values())
        if not apps:messagebox.showinfo('No updates','No verified updates are currently available.');return
        self.start_updates(apps)

    def start_updates(self,apps):
        if self.busy or self.self_busy or self.driver_busy or self.driver_scanning:return
        summary='\n'.join(f'• {a.name}: {a.installed} → {a.available}' for a in apps[:12])
        if len(apps)>12:summary+=f'\n…and {len(apps)-12} more'
        if not messagebox.askyesno('Confirm installation',f'Install these {len(apps)} update(s)?\n\n{summary}\n\nSave unsaved work first. Installers may request administrator permission.'):return
        self.stop=False;self.set_busy(True)
        self.queue_started=time.monotonic(); self.current_started=None
        self.completed_durations=[]; self.queue_total=len(apps); self.queue_completed=0; self.queue_failed=0; self.queue_active=True
        self.progressbar.configure(mode='determinate',value=0)
        self.queue_results=[]
        self.progress_title.set(f'Preparing {len(apps)} update(s)')
        self.progress_detail.set('Estimating time after the first update finishes.')
        def work():
            for a in apps:
                if self.stop:break
                self.events.put(('install_start',a.name))
                try:ok,msg=update_one(a,confirm=True)
                except Exception as exc:
                    ok,msg=False,f'Unexpected update error: {exc}'
                self.events.put(('result',(a,ok,msg)))
            self.events.put(('done',None))
        threading.Thread(target=work,daemon=True).start()

    def rescan_after_update(self):
        try:
            self.events.put(('scan',inventory()))
        except Exception as exc:
            self.events.put(('rescan_error',str(exc)))

    def show_results(self):
        self.results_frame.pack(fill='x',before=self.status,pady=(8,0))
        self.results_title.set(f'Update session: {len(self.queue_results)} attempted, {self.queue_failed} failed/unverified')
        self.results_text.configure(state='normal')
        self.results_text.delete('1.0','end')
        for name,ok,msg in self.queue_results:
            self.results_text.insert('end',('OK' if ok else 'CHECK')+f'  {name}: {msg}\n')
        self.results_text.configure(state='disabled')

    def cancel(self):
        self.stop=True;self.status.set('Stopping after the current installer finishes; it will not be terminated.')

    @staticmethod
    def format_duration(seconds):
        seconds=max(0,int(seconds))
        hours,rem=divmod(seconds,3600); minutes,secs=divmod(rem,60)
        return f'{hours}h {minutes}m' if hours else (f'{minutes}m {secs}s' if minutes else f'{secs}s')

    def tick_progress(self):
        if not self.queue_active or self.queue_started is None:return
        elapsed=time.monotonic()-self.queue_started
        if self.completed_durations and self.queue_completed < self.queue_total:
            average=sum(self.completed_durations)/len(self.completed_durations)
            current_elapsed=(time.monotonic()-self.current_started) if self.current_started is not None else 0
            remaining=max(0,average-current_elapsed)+max(0,self.queue_total-self.queue_completed-1)*average
            estimate='Estimated remaining ~'+self.format_duration(remaining)
        elif self.queue_completed==self.queue_total:
            estimate='Finishing…'
        else:estimate='Time remaining: calculating after first update'
        current=(time.monotonic()-self.current_started) if self.current_started is not None else 0
        if self.current_started is not None and self.completed_durations:
            avg=max(1,sum(self.completed_durations)/len(self.completed_durations)); fraction=min(.92,current/avg)
            shown=(self.queue_completed+fraction)/max(1,self.queue_total)*100
            self.progressbar.configure(mode='determinate',value=shown)
        self.progress_detail.set(f'{self.queue_completed}/{self.queue_total} finished  •  Elapsed {self.format_duration(elapsed)}  •  {estimate}')

    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='app_check':
                    self.self_busy=False
                    self.release=data
                    self.app_update_status.set('Version '+data['version']+' available.' if data else 'You have the latest published version.')
                    if self.page=='App updates':self.show_app_updates()
                elif kind=='app_progress':
                    received,total=data
                    if total:
                        self.app_update_progress.set(min(100,100*received/total))
                        self.app_update_detail.set(f'{received/1048576:.1f} / {total/1048576:.1f} MB downloaded')
                    else:
                        self.app_update_detail.set(f'{received/1048576:.1f} MB downloaded (total unknown)')
                elif kind=='app_error':
                    self.self_busy=False
                    self.app_update_status.set('Self-update: '+data)
                    self.app_update_detail.set('Download or verification failed')
                    if self.page=='App updates':self.show_app_updates()
                elif kind=='app_staged':
                    self.self_busy=False
                    self.app_update_progress.set(100)
                    self.app_update_detail.set('Download complete and package validated; preparing restart…')
                    helper=Path(__file__).resolve().parent/'update_helper.py'
                    try:
                        subprocess.Popen([sys.executable,str(helper),str(data),str(helper.parent),str(os.getpid())],cwd=str(helper.parent),close_fds=True)
                        self.destroy()
                    except Exception as exc:self.app_update_status.set('Cannot start update helper: '+str(exc))
                elif kind=='driver_offers':
                    self.driver_busy=False;self.driver_offers=data;self.driver_selected=set()
                    self.driver_note.set(f'{len(data)} optional driver update(s) offered by Windows Update.' if data else 'No optional driver updates currently offered by Windows Update.')
                    if self.page=='Driver updates':self.show_drivers()
                elif kind=='driver_offers_error':
                    self.driver_busy=False;self.driver_note.set('Windows Update scan failed: '+data)
                    if self.page=='Driver updates':self.render_driver_offers()
                elif kind=='driver_install_progress':
                    self.driver_note.set(data)
                elif kind=='driver_install_result':
                    d,result,error=data
                    message=error or ('Result code '+str(result['result'])+('; restart required' if result.get('reboot') else ''))
                    try:record_result({'time':datetime.now(timezone.utc).isoformat(),'name':d['title'],'package_id':d['id'],'source':'Windows Update Driver','result':'failed' if error else 'installer completed' if result['result']==2 else 'completed with errors/restart','message':message})
                    except OSError:pass
                    self.driver_note.set(d['title']+': '+message)
                elif kind=='driver_install_done':
                    self.driver_busy=False;self.driver_selected.clear();self.driver_note.set('Driver queue finished. Check Activity for results; rescan to confirm remaining updates.')
                    if self.page=='Driver updates':self.render_driver_offers()
                elif kind=='drivers':
                    self.driver_scanning=False;self.drivers=data
                    if self.page=='Driver updates':self.show_drivers()
                elif kind=='driver_error':
                    self.driver_scanning=False;self.status.set('Driver scan failed: '+data)
                    if self.page=='Driver updates':self.show_drivers()
                elif kind=='scan':
                    self.registry,updates,error=data
                    self.updates={f'{a.source}:{a.package_id}':a for a in updates}
                    self.selected.clear()
                    if self.refreshing_after_update:
                        self.refreshing_after_update=False
                        self.status.set(f'Post-update rescan: {len(updates)} updates still offered. ' + (error or 'See update results for details.'))
                    else:
                        self.status.set(f'Scan finished. {len(self.registry)} registry entries; {len(updates)} available updates. {error}')
                    self.set_busy(False)
                elif kind=='uninstall_start':
                    self.current_started=time.monotonic()
                    self.progress_title.set(f'Uninstalling: {data} ({self.queue_completed+1}/{self.queue_total})')
                    self.progressbar.configure(mode='determinate',value=100*self.queue_completed/max(1,self.queue_total))
                    self.status.set(f'Uninstalling {data}…')
                elif kind=='uninstall_result':
                    a,ok,msg=data
                    if self.current_started is not None:self.completed_durations.append(time.monotonic()-self.current_started)
                    self.current_started=None;self.queue_completed+=1
                    if not ok:self.queue_failed+=1
                    self.queue_results.append((a.name,ok,msg))
                    self.progressbar.configure(mode='determinate',value=100*self.queue_completed/max(1,self.queue_total))
                    self.status.set(f'{a.name}: {msg}')
                    try:record_result({'time':datetime.now(timezone.utc).isoformat(),'name':a.name,'package_id':a.package_id,'source':a.source,'result':'uninstalled' if ok else 'uninstall failed','message':msg})
                    except OSError:pass
                elif kind=='uninstall_done':
                    self.queue_active=False;self.set_busy(False)
                    self.progressbar.configure(mode='determinate',value=100)
                    self.progress_title.set('Uninstall complete')
                    self.progress_detail.set(f'{self.queue_completed-self.queue_failed}/{self.queue_total} uninstalled successfully  •  {self.queue_failed} failed')
                    self.show_results()
                    self.refreshing_after_update=True;self.set_busy(True)
                    threading.Thread(target=self.rescan_after_update,daemon=True).start()
                elif kind=='install_start':
                    self.current_started=time.monotonic()
                    self.progress_title.set(f'Installing: {data} ({self.queue_completed+1}/{self.queue_total})')
                    self.progressbar.configure(mode='determinate',value=100*self.queue_completed/max(1,self.queue_total))
                    self.status.set(f'Installing {data}… Installer-specific download progress is not available.')
                elif kind=='status':self.status.set(data)
                elif kind=='result':
                    a,ok,msg=data
                    if self.current_started is not None:self.completed_durations.append(time.monotonic()-self.current_started)
                    self.current_started=None;self.queue_completed+=1
                    if not ok:self.queue_failed+=1
                    self.queue_results.append((a.name,ok,msg))
                    try:record_result({'time':datetime.now(timezone.utc).isoformat(),'name':a.name,'package_id':a.package_id,'source':a.source,'installed_before':a.installed,'target':a.available,'result':'confirmed by WinGet' if ok else 'failed or unverified','message':msg})
                    except OSError as exc:self.status.set('Could not save update history: '+str(exc))
                    self.progressbar.stop()
                    self.progressbar.configure(mode='determinate',value=100*self.queue_completed/max(1,self.queue_total))
                    self.progress_title.set(f'Finished {self.queue_completed} of {self.queue_total} updates')
                    self.status.set(f'{a.name}: {msg}')
                elif kind=='done':
                    self.queue_active=False;self.set_busy(False)
                    elapsed=self.format_duration(time.monotonic()-self.queue_started) if self.queue_started is not None else 'unknown'
                    self.progress_title.set('Queue stopped' if self.stop else 'Update queue finished')
                    self.progressbar.stop()
                    self.progressbar.configure(mode='determinate',value=100*self.queue_completed/max(1,self.queue_total))
                    self.progress_detail.set(f'{self.queue_completed}/{self.queue_total} attempted  •  {self.queue_failed} failed  •  Total elapsed {elapsed}'+('  •  Remaining updates skipped' if self.stop else ''))
                    self.status.set(f'{self.queue_completed-self.queue_failed} verified/up-to-date, {self.queue_failed} failed or unverified. See results below.')
                    self.progress_title.set('Update results — ' + ('stopped' if self.stop else 'complete'))
                    self.show_results()
                    self.refreshing_after_update=True
                    self.set_busy(True)
                    threading.Thread(target=self.rescan_after_update,daemon=True).start()
                elif kind=='rescan_error':
                    self.refreshing_after_update=False
                    self.set_busy(False)
                    self.status.set('Post-update rescan failed: '+data+'; previous results are preserved.')
                elif kind=='error':self.set_busy(False);self.status.set('Error: '+data)
        except queue.Empty:pass
        self.tick_progress()
        self.after(250,self.poll)

if __name__=='__main__':SupaUpdater().mainloop()