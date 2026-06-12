%% Klasse fuer Thesen an der FFHS

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{ffhsthesis}[2013/09/20 v0.1 Klasse fuer FFHS Thesen]
\LoadClass[11pt,a4paper,bibliography=totoc,listof=totoc]{scrreprt}
\ProcessOptions\relax

\RequirePackage[T1]{fontenc}
\RequirePackage{graphicx}
\RequirePackage{varwidth}

\RequirePackage{setspace}
\onehalfspacing

\RedeclareSectionCommand[
  beforeskip=0.5\baselineskip, % Space before chapter title
  afterskip=0.5\baselineskip   % Space after chapter title
]{chapter}

\RequirePackage[left=3cm, right=2.5cm, top=3cm, bottom=2.5cm]{geometry}


\RequirePackage{helvet}
\renewcommand{\familydefault}{\sfdefault}

\RequirePackage[english,ngerman]{babel}

\RequirePackage{layout}

\newcommand{\@dokumentTyp}{Entwurf}
\newcommand{\dokumentTyp}[1]{\gdef\@dokumentTyp{#1}}

\newcommand{\@studiengang}{XY}
\newcommand{\studiengang}[1]{\gdef\@studiengang{#1}}

\newcommand{\@wohnort}{}
\newcommand{\wohnort}[1]{\gdef\@wohnort{#1}}

\newcommand{\@referent}{}
\newcommand{\@referent@in}{Referent(in)}
\newcommand{\referent}[1]{\gdef\@referent@in{Referent} \gdef\@referent{#1}}
\newcommand{\referentin}[1]{\gdef\@referent@in{Referentin} \gdef\@referent{#1}}

\newcommand{\@titelbild}{}
\newcommand{\titelbild}[2][]{\gdef\@titelbild{\includegraphics[#1]{#2}}}

\newcommand{\@eingereichtBei}{}
\newcommand{\eingereichtBei}[1]{\gdef\@eingereichtBei{#1}}

\renewcommand{\dedication}[1]{\gdef\@dedication{\ \vfill\begin{center}#1\end{center}\vfill\vfill\ \newpage}}

\titlehead{
\begin{varwidth}[t][2cm][c]{5cm}
\includegraphics[height=2cm]{FFHS_Logo.jpg}
\end{varwidth}
\hfill 
\begin{varwidth}[t][2cm][c]{7cm}
\begin{flushright}
\normalfont
Fernfachhochschule Schweiz\\
Studiengang \@studiengang 
\vfill\phantom{.}
\end{flushright}
\end{varwidth}
}

\renewcommand\maketitle{
\setcounter{page}{0}

\begin{titlepage}
\thispagestyle{headings}
\markright{\protect\@titlehead}



\begin{center}

\vspace*{2cm}

\bfseries
\Huge \@title 

\vspace{1ex}
\Large 
\@subtitle 

\vfill
\@titelbild
\vfill
\vfill

\@dokumentTyp\ im Studiengang \@studiengang

\vspace{1ex}

von

\vspace{1ex}
\@author

\vspace{1cm}
\normalsize

\vspace{1ex}
\phantom{.}
\hfill
\begin{varwidth}[t]{6cm}
Eingereicht bei:

\vspace{0.5ex}
\mdseries\normalsize
\@eingereichtBei
\end{varwidth}
\hfill
\hfill
\begin{varwidth}[t]{6cm}
\@referent@in:

\vspace{0.5ex}
\mdseries\normalsize
\@referent
\end{varwidth}
\hfill
\phantom{.}

\vspace{5ex}
\@wohnort

\end{center}
\end{titlepage}

\@dedication
}

\makeatletter
\renewcommand*{\chapter}{%
    \if@openright\relax\else\relax\fi % Remove the default behavior
    \thispagestyle{plain}%
    \global\@topnum\z@ % No floats at top of page
    \@afterindentfalse % No indent after chapter
    \secdef\@chapter\@schapter}

\pagenumbering{roman}

\newcommand{\startThesis}{\newpage\pagenumbering{arabic}\setcounter{page}{1}}

