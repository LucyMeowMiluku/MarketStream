# Literature Review: Real-Time Streaming Anomaly Detection in Financial Markets

## 1. Introduction

The growth of algorithmic and high-frequency trading has significantly increased the velocity of financial market data. Modern markets generate continuous streams of price, volume, and news information, creating both opportunities and challenges for real-time monitoring (Aldridge, 2013). Detecting anomalous market behavior — such as sudden price dislocations, unusual volume spikes, or sentiment-driven events — is important for risk management, regulatory surveillance, and trading operations (Cao, Chen, Kou & Peng, 2023).

Batch-oriented analytics pipelines, which periodically process accumulated data, are often too slow for this purpose. By the time anomalies are detected through batch analysis, market conditions may have already changed substantially (Gama, Zliobaite, Bifet, Pechenizkiy & Bouchachia, 2014). This motivates a shift toward streaming architectures that process data as it arrives, reducing detection latency to the sub-minute range.

Furthermore, the multimodal nature of market signals introduces additional complexity. Price and volume data alone may not fully characterize market state; news sentiment and cross-asset correlations can provide additional context (Bollen, Mao & Zeng, 2011). Financial time series are also inherently non-stationary — the statistical properties of market data change over time due to shifting macroeconomic conditions, regulatory events, and evolving market structure (Tsay, 2010). An effective detection system must therefore operate in real time while also adapting to these distribution shifts.

This literature review surveys the algorithmic and architectural foundations relevant to the MarketStream platform. MarketStream is designed as a real-time streaming financial analytics system that combines multiple anomaly detection methods, sentiment analysis, and concept drift adaptation within a Kafka-based pipeline. This review provides the theoretical grounding for the system's design choices. For each topic, we review relevant prior work, compare competing approaches, and explain which methods are adopted in MarketStream and why. It should be noted that MarketStream is an evolving system — the architecture described here represents the target design, with some components still under active development and refinement.

## 2. Streaming Data Architectures

### 2.1 Lambda and Kappa Architectures

Marz and Warren (2015) introduced the Lambda Architecture, which maintains parallel batch and speed layers to balance latency and accuracy. The batch layer periodically reprocesses the entire dataset, while the speed layer handles recent data with lower latency. While this design is robust, maintaining two separate processing paths adds significant operational complexity.

Kreps (2014) proposed the Kappa Architecture as an alternative. The idea is that a single stream processing layer, backed by a replayable event log, can handle both real-time and historical reprocessing. By treating the event log as the source of truth and replaying it with updated logic when needed, the Kappa Architecture avoids the dual-codebase problem of Lambda while retaining reprocessing capability.

### 2.2 Apache Kafka and Event Streaming

Apache Kafka (Kreps, Narkhede & Rao, 2011) has become the standard platform for distributed event streaming. Kafka provides a durable, partitioned commit log with strong ordering guarantees within partitions. It supports high-throughput ingestion with configurable retention, making it useful both as a messaging system and as a storage layer for event-sourced architectures. Recent releases introduced KRaft mode, which replaces the ZooKeeper dependency with a self-managed metadata quorum, simplifying deployment (Apache Software Foundation, 2023).

### 2.3 Stream Processing Engines

Several stream processing frameworks exist for building stateful computations on top of Kafka. Apache Flink (Carbone et al., 2015) provides exactly-once semantics and sophisticated windowing but requires a separate JVM-based cluster. Apache Spark Structured Streaming (Zaharia et al., 2013) takes a micro-batch approach, which introduces higher latency than true record-at-a-time processing. Kafka Streams offers lightweight, embeddable processing without a separate cluster, but it is also JVM-only (Sax, Castellanos, Hueske & Kalavri, 2018).

Quix Streams (Quix, 2023) is a Python-native stream processing library providing tumbling, hopping, and sliding window operations with configurable grace periods. It operates directly against Kafka topics without requiring a separate processing cluster. For our use case, this is a practical advantage: since all anomaly detection models (scikit-learn, PyTorch, river) run in Python, using a Python-native stream processor avoids the friction of cross-language integration and keeps the entire pipeline in one runtime.

> **Adopted in MarketStream**: MarketStream follows the Kappa Architecture pattern — a single streaming layer with no separate batch processing path. Apache Kafka in KRaft mode serves as the event backbone, with four topics (`raw.prices`, `raw.news_sentiment`, `stream.features`, `stream.anomalies`) connecting five independently-running Python processes. Quix Streams provides tumbling windows with a 5-minute duration and 30-second grace period for feature aggregation. The choice of Quix Streams over Flink or Spark is driven primarily by integration considerations: the downstream ML pipeline uses PyTorch, scikit-learn, and river, all of which are Python libraries. A JVM-based stream processor would have required a separate service boundary and serialization overhead between the feature computation and scoring stages.

## 3. Anomaly Detection Methods

Anomaly detection in time series has been studied extensively, with methods spanning statistical, machine learning, and deep learning approaches. Chandola, Banerjee, and Kumar (2009) provide a taxonomy that distinguishes point anomalies (individual outliers), contextual anomalies (abnormal given temporal context), and collective anomalies (anomalous subsequences). Financial anomaly detection must contend with all three types, often simultaneously.

Figure 1 provides an overview of the methods reviewed in this chapter. Methods adopted in MarketStream are highlighted in blue.

![Figure 1. Taxonomy of Reviewed Methods](fig1_taxonomy.png)

### 3.1 Statistical Methods

**EWMA (Exponentially Weighted Moving Average).** Roberts (1959) introduced EWMA control charts for detecting shifts in process means. EWMA assigns exponentially decaying weights to past observations, with a smoothing parameter controlling the decay rate. Anomaly detection works by measuring how far a new observation deviates from the running mean, expressed as a z-score. EWMA is computationally cheap (O(1) per update), needs no training data, and adapts gradually to slow distribution changes through its exponential forgetting. On the other hand, it treats each feature independently and cannot capture multivariate interactions or temporal patterns beyond simple level shifts (Montgomery, 2012).

**CUSUM (Cumulative Sum).** Page (1954) proposed CUSUM for detecting small, sustained shifts in process parameters. CUSUM accumulates deviations from a target value and signals a change when the cumulative sum exceeds a threshold. While effective for persistent mean shifts, CUSUM is less suited to the transient, spike-like anomalies common in financial markets and requires careful tuning of its reference value and decision interval (Basseville & Nikiforov, 1993).

> **Adopted in MarketStream**: MarketStream uses EWMA as its statistical baseline detector. The implementation maintains per-ticker running mean and variance estimates for four features (price change rate, total volume, average sentiment, sentiment shift) and scores each observation as the negated maximum z-score across features. EWMA was chosen for its immediate usability — it begins producing meaningful scores from the second observation onward, with no training phase or historical data requirement. In the ensemble, it serves as a fast, lightweight first line of detection that complements the more complex ML-based detectors.

### 3.2 Machine Learning Methods

**Isolation Forest.** Liu, Ting, and Zhou (2008) introduced Isolation Forest, which detects anomalies by measuring how easily a data point can be separated from the rest of the data. The algorithm builds an ensemble of random binary trees (isolation trees), each recursively partitioning the feature space with random splits. Anomalies, being few and different from the majority, tend to be isolated in fewer splits, resulting in shorter average path lengths. Isolation Forest trains in O(t * n * log(psi)) time and scores each point in O(t * log(psi)), where t is the number of trees and psi is the subsample size. It makes no distributional assumptions, handles high-dimensional data well, and is robust to irrelevant features (Liu, Ting & Zhou, 2012). The main limitation for streaming applications is that it is a batch-trained model — once trained, it does not update as new data arrives, so it may become stale as market conditions change (Hariri, Kind & Brunner, 2019).

**One-Class SVM.** Scholkopf et al. (2001) proposed One-Class SVM, which learns a decision boundary in kernel space that separates normal data from the origin. However, its O(n^2) to O(n^3) training complexity makes it impractical for large or streaming datasets without aggressive subsampling, and it is sensitive to kernel and hyperparameter choices (Tax & Duin, 2004).

> **Adopted in MarketStream**: MarketStream uses scikit-learn's Isolation Forest (200 trees, contamination=0.05) as the batch-trained ensemble component. The model is trained on 30 days of historical price and synthetic sentiment data, serialized via joblib, and loaded at runtime. Isolation Forest was chosen over One-Class SVM primarily for its inference speed and its relatively low sensitivity to hyperparameter settings — in our testing, the default configuration produced reasonable results without extensive tuning. As a batch model, it captures what "normal" looks like based on historical data, but it cannot adapt to market regime changes on its own. This is why the ensemble also includes streaming detectors that can.

### 3.3 Deep Learning Methods

**LSTM Autoencoders.** Malhotra, Vig, Shroff, and Agarwal (2016) showed that LSTM autoencoders can detect anomalies in multivariate time series by learning to reconstruct normal temporal patterns. The encoder compresses a fixed-length input sequence into a latent representation, and the decoder reconstructs the original sequence from this representation. Points or subsequences with high reconstruction error (measured by MSE) are flagged as anomalous. Unlike point-based methods like Isolation Forest, LSTM autoencoders capture dependencies across time steps — they can detect anomalies that only become apparent when viewed as part of a sequence (Hundman, Constantinou, Laporte, Colwell & Soderstrom, 2018).

**Variational Autoencoders (VAE).** Kingma and Welling (2014) introduced VAEs, which learn a probabilistic latent space and can provide uncertainty estimates alongside reconstruction error. For time series anomaly detection, this is appealing in principle, but VAEs require careful tuning of the KL-divergence weight and are more computationally expensive than deterministic autoencoders (Park, Hoshi & Kegl, 2018).

**Transformer-based methods.** Xu et al. (2022) proposed the Anomaly Transformer for time series, which uses an association discrepancy mechanism to identify anomalies. While these models show strong results on benchmark datasets, they are substantially more expensive to train and run inference on. In a real-time streaming context where each feature vector must be scored within seconds and the system runs on modest hardware, the quadratic attention complexity of Transformers (O(seq^2 * d)) becomes a practical bottleneck (Tuli, Casale & Jennings, 2022).

> **Adopted in MarketStream**: MarketStream adopts an LSTM Autoencoder as its temporal detector. The architecture uses a configurable hidden dimension (default 32) and sequence length (default 12 windows, representing one hour of 5-minute data). The detector maintains a per-ticker sliding buffer; once the buffer fills, it feeds the sequence through the encoder-decoder and reports the negated MSE as the anomaly score. The LSTM Autoencoder was chosen over Transformer-based alternatives because our sequences are short (12 steps) and the feature dimension is small (4 features) — at this scale, Transformers offer little advantage over LSTMs while being significantly heavier to deploy in a streaming loop. The LSTM is the only detector in the ensemble that captures temporal patterns (e.g., a gradual but unusual trend across multiple windows), which is why it is included despite its warm-up period and higher computational cost.

### 3.4 Online and Incremental Methods

**Half-Space Trees (HST).** Tan, Ting, and Liu (2011) proposed Half-Space Trees as a streaming variant of Isolation Forest for one-pass anomaly detection. Like Isolation Forest, HST uses an ensemble of random binary trees, but the trees are pre-built with random axis-aligned splits before any data is observed. Each leaf node maintains mass counters for a reference window and a current window. When the current window fills, it replaces the reference window, allowing the model to adapt to distribution changes without explicit retraining. HST has O(h) per-point complexity (where h is tree height) and constant memory, making it practical for continuous streaming (Ting, Washio & Wells, 2020).

**River library.** Montiel et al. (2021) developed River, a Python library for online machine learning that provides streaming implementations of algorithms including Half-Space Trees and various drift detectors (ADWIN, DDM, KSWIN) under a consistent `learn_one`/`predict_one` API. The library handles the complexities of online learning while providing a scikit-learn-inspired interface.

> **Adopted in MarketStream**: MarketStream uses Half-Space Trees via River's implementation (25 trees, height 6, window size 50). Unlike the batch-trained Isolation Forest, HST updates incrementally with each incoming feature vector, enabling it to track distributional changes in real time. This creates a natural division of labor in the ensemble: Isolation Forest captures the global structure of normal behavior based on historical data, while HST tracks what "normal" looks like recently. If the market enters a new regime, Isolation Forest may lag until it is retrained, but HST adapts within its sliding window. This complementary pairing is a key design choice in the ensemble.

## 4. Sentiment Analysis in Finance

### 4.1 NLP for Financial Text

Research has shown that news sentiment has measurable short-term predictive power for price movements. Tetlock (2007) demonstrated that media pessimism predicts downward pressure on aggregate market prices using a dictionary-based approach. Bollen, Mao, and Zeng (2011) showed that Twitter mood — particularly a "calm" dimension — improved prediction of Dow Jones movements, achieving 87.6% directional accuracy. These findings motivate the inclusion of sentiment as a feature in anomaly detection, since a sudden shift in sentiment may precede or accompany unusual price behavior.

### 4.2 Transformer-Based Financial Sentiment

Dictionary-based and bag-of-words approaches to financial sentiment analysis suffer from domain specificity. Words like "bull," "call," and "short" carry financial meanings that generic sentiment lexicons misclassify (Loughran & McDonald, 2011). Pre-trained language models, particularly BERT (Devlin et al., 2019), enabled transfer learning approaches that handle contextual semantics more effectively.

Araci (2019) introduced FinBERT, a BERT model further pre-trained on financial text (10-K filings, analyst reports, financial news) and fine-tuned on the Financial PhraseBank dataset (Malo, Sinha, Korhonen, Wallenius & Takala, 2014). FinBERT achieves strong performance on financial sentiment classification compared to general-purpose BERT, particularly for domain-specific terminology (Huang, Wang & Yang, 2023).

> **Adopted in MarketStream**: MarketStream uses FinBERT (ProsusAI/finbert via Hugging Face Transformers) to score news headlines in real time. The news producer polls headlines every 120 seconds and runs each through FinBERT, mapping scores to a [-1, 1] range. These sentiment scores are then used as features for anomaly detection — the online scorer computes both the average recent sentiment and the sentiment shift (difference between recent and older headline averages) for each ticker. FinBERT was chosen over dictionary-based methods because financial headlines frequently use domain-specific language that generic lexicons handle poorly. A headline like "Tesla shorts get burned as stock rallies" would likely be misclassified by a general-purpose sentiment tool.

## 5. Ensemble Methods for Anomaly Detection

### 5.1 Heterogeneous Ensembles

Aggarwal and Sathe (2017) distinguish between sequential, independent, and heterogeneous ensembles for outlier detection. Heterogeneous ensembles combine fundamentally different detector types — statistical, tree-based, neural — to exploit their complementary strengths. The main challenge is score normalization, since different detectors produce scores on different scales (Zimek, Campello & Sander, 2014).

### 5.2 Score Combination Strategies

Rayana and Akoglu (2016) compared score combination strategies for unsupervised outlier ensembles (averaging, maximization, rank-based methods) and found that simple weighted averaging is competitive with more complex strategies when detectors are diverse and individually performant. Zhao, Nasrullah, and Li (2019) reached similar conclusions in their PyOD toolkit evaluation.

> **Adopted in MarketStream**: MarketStream combines its four detectors through weighted voting in an `EnsembleDetector` class. All detectors implement a common interface producing scores where lower values indicate greater anomaly severity, which simplifies score combination — no additional normalization is needed. The weights (EWMA 0.2, HST 0.3, Isolation Forest 0.3, LSTM 0.2) reflect a deliberate design choice: the two tree-based detectors receive higher weight because they capture multivariate feature interactions, while EWMA (univariate) and LSTM (requires warm-up) receive lower weight. The ensemble handles the LSTM's warm-up period by detecting its neutral zero-return score and excluding it from the weighted average until it has accumulated enough observations. This is a practical engineering consideration that the academic ensemble literature does not typically address — in a live streaming system, not all detectors are ready simultaneously.

## 6. Concept Drift and Model Maintenance

### 6.1 The Problem of Non-Stationarity

Financial time series are non-stationary by nature. The statistical properties of market data change over time due to regime shifts, structural breaks, and evolving market microstructure (Tsay, 2010). A model trained on historical data will gradually degrade as conditions drift from the training distribution — a phenomenon known as concept drift (Gama et al., 2014). Drift may be gradual (slow evolution), sudden (abrupt regime change), or recurring (seasonal patterns).

### 6.2 Drift Detection Methods

**ADWIN (Adaptive Windowing).** Bifet and Gavalda (2007) proposed ADWIN, an adaptive sliding window algorithm that detects distribution changes by maintaining a variable-length window. ADWIN shrinks its window when it detects a statistically significant difference between two sub-windows, controlled by a delta parameter. It requires no prior knowledge of the expected drift rate and provides theoretical guarantees on false positive and negative rates.

**DDM (Drift Detection Method).** Gama, Medas, Castillo, and Rodrigues (2004) introduced DDM, which monitors the error rate of a supervised classifier and triggers drift detection when the error rate exceeds statistical bounds. However, DDM requires labeled data — a significant limitation in our setting, since financial anomalies rarely come with ground-truth labels.

**KSWIN.** Raab, Schleif, Biehl, and Hammer (2020) proposed KSWIN, which uses the Kolmogorov-Smirnov test to compare reference and sliding window distributions. KSWIN is non-parametric but computationally more expensive than ADWIN at equivalent sensitivity levels.

### 6.3 Retraining Strategies

When drift is detected, models must be updated. Options include full retraining on recent data (simple but expensive), incremental updates (efficient but may propagate errors), and ensemble approaches that maintain models trained on different time windows (Kolter & Maloof, 2007). Scheduled periodic retraining is a pragmatic middle ground.

> **Adopted in MarketStream**: MarketStream uses two complementary drift-handling strategies. First, ADWIN (via River) monitors four features per ticker for distribution shifts with a delta sensitivity of 0.002. ADWIN was chosen over DDM because our system operates in an unsupervised setting — there are no labeled anomaly data to compute error rates against. When drift is detected, events are logged to a `drift_events` table for analysis and can serve as triggers for retraining. Second, the Isolation Forest supports scheduled retraining: fresh historical data is downloaded, a new model is trained and versioned, and the active model is swapped. Additionally, two of the four ensemble detectors — HST and EWMA — are inherently adaptive. HST's sliding reference window and EWMA's exponential forgetting both continuously adjust to recent data, providing implicit drift handling even before explicit retraining occurs. This layered approach (adaptive detectors for short-term drift + ADWIN monitoring for systematic shifts + periodic retraining for batch models) is designed to handle the different timescales at which market regimes change.

## 7. Research Gap

Each of the components reviewed above — streaming architectures, anomaly detection algorithms, sentiment analysis, ensemble methods, and drift detection — has been studied extensively as an individual topic. However, integrating them into a single end-to-end streaming system raises challenges that are not well-addressed in the existing literature.

Most financial anomaly detection work focuses on a single method applied to offline datasets: statistical approaches evaluated on historical benchmarks (Fisch, Eckley & Fearnhead, 2022), batch-trained ML models applied retrospectively (Hilal, Gadsden & Yawney, 2022), or deep learning models that assume stationary distributions (Tuli, Casale & Jennings, 2022). Systems that do combine multiple detectors rarely incorporate real-time sentiment enrichment or drift adaptation.

Figure 2 illustrates the target MarketStream architecture, showing where each adopted method fits within the streaming pipeline.

![Figure 2. MarketStream System Architecture with Adopted Methods](fig2_architecture.png)

The specific gap that MarketStream aims to address is the challenge of managing heterogeneous detectors in a live streaming environment. In a real-time Kappa-style pipeline, several practical issues arise that offline evaluations do not encounter: how to handle detectors that warm up at different rates (the LSTM needs 12 observations before it can score, while EWMA starts immediately); how to weight detectors whose reliability changes as market conditions shift; and how to detect and respond to concept drift without interrupting the data flow or requiring labeled data. These are engineering challenges as much as algorithmic ones, and the combination of adaptive streaming detectors (EWMA, HST) with batch-trained models (Isolation Forest, LSTM Autoencoder), real-time sentiment features, and unsupervised drift monitoring (ADWIN) within a single pipeline is, to our knowledge, not well-represented in the current literature.

## 8. Summary Table

| Method | Type | Complexity (per point) | Latency | Online Adaptive | Interpretability | Adopted |
|--------|------|----------------------|---------|-----------------|------------------|---------|
| EWMA (Roberts, 1959) | Statistical | O(1) | Ultra-low | Yes (exponential decay) | High (z-scores) | **Yes** |
| CUSUM (Page, 1954) | Statistical | O(1) | Ultra-low | Yes | High | No |
| Isolation Forest (Liu et al., 2008) | ML ensemble | O(t * log psi) | Low | No (batch) | Medium (path lengths) | **Yes** |
| One-Class SVM (Scholkopf et al., 2001) | ML kernel | O(n_sv * d) | Medium | No (batch) | Low | No |
| LSTM Autoencoder (Malhotra et al., 2016) | Deep learning | O(seq * h^2) | Medium | No (batch, buffered) | Low (reconstruction error) | **Yes** |
| VAE (Kingma & Welling, 2014) | Deep learning | O(seq * h^2) | Medium | No (batch) | Medium (latent + error) | No |
| Anomaly Transformer (Xu et al., 2022) | Deep learning | O(seq^2 * d) | High | No (batch) | Medium | No |
| Half-Space Trees (Tan et al., 2011) | Online ML | O(t * h) | Ultra-low | Yes (sliding window) | Medium | **Yes** |
| FinBERT (Araci, 2019) | NLP transformer | O(n^2) per headline | Low | No (pre-trained) | High (label + score) | **Yes** |
| ADWIN (Bifet & Gavalda, 2007) | Drift detection | O(log W) amortized | Ultra-low | Yes (adaptive window) | High (change point) | **Yes** |
| DDM (Gama et al., 2004) | Drift detection | O(1) | Ultra-low | Yes | High | No |
| Weighted Voting Ensemble | Meta-method | Sum of components | Sum of components | Partial | Medium (per-detector scores) | **Yes** |

**Key**: *t* = number of trees, *psi* = subsample size, *h* = hidden dimension, *seq* = sequence length, *d* = feature dimension, *n_sv* = number of support vectors, *W* = window size.

## References

Aggarwal, C. C., & Sathe, S. (2017). *Outlier Ensembles: An Introduction*. Springer.

Aldridge, I. (2013). *High-Frequency Trading: A Practical Guide to Algorithmic Strategies and Trading Systems* (2nd ed.). Wiley.

Apache Software Foundation. (2023). KIP-500: Replace ZooKeeper with a Self-Managed Metadata Quorum. Apache Kafka Improvement Proposals.

Araci, D. (2019). FinBERT: Financial Sentiment Analysis with Pre-Trained Language Models. *arXiv preprint arXiv:1908.10063*.

Basseville, M., & Nikiforov, I. V. (1993). *Detection of Abrupt Changes: Theory and Application*. Prentice Hall.

Bifet, A., & Gavalda, R. (2007). Learning from time-changing data with adaptive windowing. In *Proceedings of the 2007 SIAM International Conference on Data Mining* (pp. 443-448). SIAM.

Bollen, J., Mao, H., & Zeng, X. (2011). Twitter mood predicts the stock market. *Journal of Computational Science*, 2(1), 1-8.

Cao, L., Chen, Y., Kou, G., & Peng, Y. (2023). Anomaly detection in financial markets: A survey. *ACM Computing Surveys*, 55(8), 1-36.

Carbone, P., Katsifodimos, A., Ewen, S., Markl, V., Haridi, S., & Tzoumas, K. (2015). Apache Flink: Stream and batch processing in a single engine. *Bulletin of the IEEE Computer Society Technical Committee on Data Engineering*, 36(4), 28-38.

Chandola, V., Banerjee, A., & Kumar, V. (2009). Anomaly detection: A survey. *ACM Computing Surveys*, 41(3), 1-58.

Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. In *Proceedings of NAACL-HLT 2019* (pp. 4171-4186).

Fama, E. F. (1970). Efficient capital markets: A review of theory and empirical work. *The Journal of Finance*, 25(2), 383-417.

Fisch, A. T. M., Eckley, I. A., & Fearnhead, P. (2022). A linear time method for the detection of collective and point anomalies on large scale locally stationary time series. *Statistical Analysis and Data Mining*, 15(2), 163-182.

Gama, J., Medas, P., Castillo, G., & Rodrigues, P. (2004). Learning with drift detection. In *Advances in Artificial Intelligence -- SBIA 2004* (pp. 286-295). Springer.

Gama, J., Zliobaite, I., Bifet, A., Pechenizkiy, M., & Bouchachia, A. (2014). A survey on concept drift adaptation. *ACM Computing Surveys*, 46(4), 1-37.

Hariri, S., Kind, M. C., & Brunner, R. J. (2019). Extended isolation forest. *IEEE Transactions on Knowledge and Data Engineering*, 33(4), 1479-1489.

Hilal, W., Gadsden, S. A., & Yawney, J. (2022). Financial fraud: A review of anomaly detection techniques and recent advances. *Expert Systems with Applications*, 193, 116429.

Huang, A. H., Wang, H., & Yang, Y. (2023). FinBERT: A large language model for extracting information from financial text. *Contemporary Accounting Research*, 40(2), 806-841.

Hundman, K., Constantinou, V., Laporte, C., Colwell, I., & Soderstrom, T. (2018). Detecting spacecraft anomalies using LSTMs and nonparametric dynamic thresholding. In *Proceedings of the 24th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining* (pp. 387-395).

Kingma, D. P., & Welling, M. (2014). Auto-encoding variational Bayes. In *Proceedings of the 2nd International Conference on Learning Representations (ICLR)*.

Kolter, J. Z., & Maloof, M. A. (2007). Dynamic weighted majority: An ensemble method for drifting concepts. *Journal of Machine Learning Research*, 8, 2755-2790.

Kreps, J. (2014). Questioning the Lambda Architecture. *O'Reilly Radar*.

Kreps, J., Narkhede, N., & Rao, J. (2011). Kafka: A distributed messaging system for log processing. In *Proceedings of the NetDB Workshop*.

Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation forest. In *Proceedings of the 2008 Eighth IEEE International Conference on Data Mining* (pp. 413-422).

Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2012). Isolation-based anomaly detection. *ACM Transactions on Knowledge Discovery from Data*, 6(1), 1-39.

Loughran, T., & McDonald, B. (2011). When is a liability not a liability? Textual analysis, dictionaries, and 10-Ks. *The Journal of Finance*, 66(1), 35-65.

Malhotra, P., Vig, L., Shroff, G., & Agarwal, P. (2016). LSTM-based encoder-decoder for multi-sensor anomaly detection. In *ICML 2016 Anomaly Detection Workshop*.

Malo, P., Sinha, A., Korhonen, P., Wallenius, J., & Takala, P. (2014). Good debt or bad debt: Detecting semantic orientations in economic texts. *Journal of the Association for Information Science and Technology*, 65(4), 782-796.

Marz, N., & Warren, J. (2015). *Big Data: Principles and Best Practices of Scalable Real-Time Data Systems*. Manning Publications.

Montgomery, D. C. (2012). *Statistical Quality Control: A Modern Introduction* (7th ed.). Wiley.

Montiel, J., Halford, M., Mastelini, S. M., Bolmier, G., Cesari, R., Grossi, M., ... & Bouchachia, A. (2021). River: Machine learning for streaming data in Python. *Journal of Machine Learning Research*, 22(110), 1-8.

Page, E. S. (1954). Continuous inspection schemes. *Biometrika*, 41(1/2), 100-115.

Park, D., Hoshi, Y., & Kegl, B. (2018). A multimodal anomaly detector for robot-assisted feeding using an LSTM-based variational autoencoder. *IEEE Robotics and Automation Letters*, 3(3), 1544-1551.

Quix. (2023). Quix Streams: A Python library for streaming data processing.

Raab, C., Schleif, F.-M., Biehl, M., & Hammer, B. (2020). Reactive soft prototype computing for concept drift streams. *Neurocomputing*, 416, 340-351.

Rayana, S., & Akoglu, L. (2016). Less is more: Building selective anomaly ensembles. *ACM Transactions on Knowledge Discovery from Data*, 10(4), 1-33.

Roberts, S. W. (1959). Control chart tests based on geometric moving averages. *Technometrics*, 1(3), 239-250.

Sax, M. J., Castellanos, G., Hueske, F., & Kalavri, V. (2018). Apache Flink and Apache Kafka Streams. In *Streams Processing Engines*. Springer.

Scholkopf, B., Platt, J. C., Shawe-Taylor, J., Smola, A. J., & Williamson, R. C. (2001). Estimating the support of a high-dimensional distribution. *Neural Computation*, 13(7), 1443-1471.

Tan, S. C., Ting, K. M., & Liu, T. F. (2011). Fast anomaly detection for streaming data. In *Proceedings of the 22nd International Joint Conference on Artificial Intelligence (IJCAI)* (pp. 1511-1516).

Tax, D. M. J., & Duin, R. P. W. (2004). Support vector data description. *Machine Learning*, 54(1), 45-66.

Tetlock, P. C. (2007). Giving content to investor sentiment: The role of media in the stock market. *The Journal of Finance*, 62(3), 1139-1168.

Ting, K. M., Washio, T., & Wells, J. R. (2020). Isolation distributional kernel: A new tool for kernel-based anomaly detection. In *Proceedings of the 26th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining* (pp. 198-206).

Tsay, R. S. (2010). *Analysis of Financial Time Series* (3rd ed.). Wiley.

Tuli, S., Casale, G., & Jennings, N. R. (2022). TranAD: Deep transformer networks for anomaly detection in multivariate time series data. *Proceedings of the VLDB Endowment*, 15(6), 1201-1214.

Xu, J., Wu, H., Wang, J., Zhao, M., Yuan, X., Ester, M., He, J., & Huang, J. (2022). Anomaly transformer: Time series anomaly detection with association discrepancy. In *Proceedings of the 10th International Conference on Learning Representations (ICLR)*.

Zaharia, M., Das, T., Li, H., Hunter, T., Shenker, S., & Stoica, I. (2013). Discretized streams: Fault-tolerant streaming computation at scale. In *Proceedings of the 24th ACM Symposium on Operating Systems Principles (SOSP)* (pp. 423-438).

Zhao, Y., Nasrullah, Z., & Li, Z. (2019). PyOD: A Python toolbox for scalable outlier detection. *Journal of Machine Learning Research*, 20(96), 1-7.

Zimek, A., Campello, R. J. G. B., & Sander, J. (2014). Ensembles for unsupervised outlier detection: Challenges and research questions. *ACM SIGKDD Explorations Newsletter*, 15(1), 11-22.
