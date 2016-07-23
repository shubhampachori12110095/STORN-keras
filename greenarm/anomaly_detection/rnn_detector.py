from keras.callbacks import ModelCheckpoint, EarlyStopping
from keras.models import Model
from keras.layers import Input, TimeDistributed, Dense, Dropout, Masking, SimpleRNN
from greenarm.util import get_logger
import time

logger = get_logger(__name__)
RecurrentLayer = SimpleRNN


class RNNAnomalyDetector(object):
    """
    The RNN Anomaly Detector is trained on a
    1 dimensional array of the loss value of
    the STORN model.
    """

    def __init__(self, n_deep_dense_input=0, num_hidden_dense=64,
                 n_deep_recurrent=1, num_hidden_recurrent=32,
                 n_deep_dense=0, activation="tanh", dropout=0.0):

        self.n_deep_dense_input = n_deep_dense_input
        self.num_hidden_dense = num_hidden_dense
        self.num_hidden_recurrent = num_hidden_recurrent
        self.n_deep_recurrent = n_deep_recurrent
        self.n_deep_dense = n_deep_dense
        self.activation = activation
        self.dropout = dropout

        self.model = None

    def build_model(self, seq_len=None):
        loss_input = Input(shape=(seq_len, 1))
        masked_input = Masking()(loss_input)

        # deep feature extraction for the loss
        deep = masked_input
        for i in range(self.n_deep_dense_input):
            deep = TimeDistributed(Dense(self.num_hidden_dense, activation=self.activation))(deep)
            if self.dropout != 0.0:
                deep = Dropout(self.dropout)(deep)

        # RNN node to process the loss time-series
        rnn = RecurrentLayer(self.num_hidden_recurrent, return_sequences=False, stateful=False)(deep)

        # deep feature extraction for the RNN output
        output = rnn
        for i in range(self.n_deep_dense):
            output = Dense(self.num_hidden_dense, activation=self.activation)(output)
            if self.dropout != 0.0:
                output = Dropout(self.dropout)(output)

        # The RNN output is in the end of a sequence, and
        # corresponds to the prediction "there was an anomaly"
        # in the whole time-series or not
        output = Dense(1, activation="sigmoid")(output)

        model = Model(input=[loss_input], output=output)
        model.compile(optimizer='rmsprop', loss='binary_crossentropy', metrics=['acc'])
        return model

    def train(self, X, y, validation_split=0.1, max_epochs=1000):
        n_samples = X.shape[0]
        seq_len = X.shape[1]

        if self.model is None:
            self.model = self.build_model(seq_len=seq_len)

        split_idx = int((1. - validation_split) * n_samples)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        checkpoint = ModelCheckpoint("best_anomaly_weights.h5", monitor='val_acc', save_best_only=True, verbose=1)
        early_stop = EarlyStopping(monitor='val_acc', patience=150, verbose=1)
        try:
            logger.debug("Beginning anomaly detector training..")
            self.model.fit(
                [X_train], y_train,
                nb_epoch=max_epochs, validation_data=([X_val], y_val),
                callbacks=[checkpoint, early_stop]
            )
        except KeyboardInterrupt:
            logger.debug("Training interrupted! Restoring best weights and saving..")

        self.model.load_weights("best_anomaly_weights.h5")
        self.save()

    def predict(self, X):
        return self.model.predict([X]) > 0.5

    def save(self, prefix=None):
        if prefix is None:
            prefix = "saved_models/RNNAnomalyDetector_%s.model" % int(time.time())

        logger.debug("Saving model to %s" % prefix)
